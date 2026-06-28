from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from backend.domain.git import ChangeStatus
from backend.domain.pathway2.normalization import GITIGNORE_OVERLAY_ENTRY, OVERLAY_FILENAME, PLACEHOLDER

"""
Return-path safety gate (Pathway 2 P2-4).

`evaluate_commit_safety` is the reusable fail-closed gate for staged content.
- Used by pathway2 safe commit today (explicit-path staging only).
- Documented seam for a future guarded `PushBranch` if ADR-0010 is later amended.
- Atlas does NOT push (ADR-0010 upheld).
"""

SERVER_CFG_NAMES = frozenset({"server.cfg"})


class SecretScannerPort(Protocol):
    def scan(self, *, path: str, content: str) -> list[Any]: ...


@dataclass(frozen=True, slots=True)
class StagedFile:
    path: str
    content: str


@dataclass(frozen=True, slots=True)
class CommitSafetyFinding:
    path: str
    line: int
    secret_type: str
    redacted_preview: str
    reason: str


@dataclass(frozen=True, slots=True)
class CommitSafetyResult:
    allowed: bool
    findings: tuple[CommitSafetyFinding, ...] = ()
    staged_paths: tuple[str, ...] = ()
    overlay_excluded: bool = True
    server_cfg_placeholder_only: bool | None = None
    blocked_paths: tuple[str, ...] = ()

    def to_report(self) -> dict[str, Any]:
        gate_status = "PASS" if self.allowed else "BLOCKED"
        summary_lines = [
            f"Files to commit: {len(self.staged_paths)}",
            f"Secret scan: {gate_status}",
            f"{OVERLAY_FILENAME} excluded (gitignored)",
        ]
        if self.server_cfg_placeholder_only is True:
            summary_lines.append("Base server.cfg: placeholders only ✓")
        elif self.server_cfg_placeholder_only is False:
            summary_lines.append("Base server.cfg: real secret values detected ✗")
        elif not any(Path(path).name == "server.cfg" for path in self.staged_paths):
            summary_lines.append("Base server.cfg: not in commit set")
        if not self.allowed:
            summary_lines.append("Commit blocked — remove or fix flagged files before committing.")
        return {
            "gate_status": gate_status,
            "allowed": self.allowed,
            "staged_paths": list(self.staged_paths),
            "overlay_excluded": self.overlay_excluded,
            "server_cfg_placeholder_only": self.server_cfg_placeholder_only,
            "findings": [
                {
                    "path": item.path,
                    "line": item.line,
                    "secret_type": item.secret_type,
                    "redacted_preview": item.redacted_preview,
                    "reason": item.reason,
                }
                for item in self.findings
            ],
            "blocked_paths": list(self.blocked_paths),
            "summary_lines": summary_lines,
            "push_seam": "evaluate_commit_safety is reusable for a future guarded PushBranch; Atlas remains commit-only per ADR-0010.",
            "manual_push_message": "Commit ready locally. Push to your branch with your git tool — Atlas does not push.",
        }

    @staticmethod
    def _normalized_path(path: str) -> str:
        return Path(path).name.replace("\\", "/")


def is_overlay_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized.endswith(f"/{OVERLAY_FILENAME}") or normalized == OVERLAY_FILENAME or normalized.endswith(f"/{GITIGNORE_OVERLAY_ENTRY}")


def select_default_return_commit_paths(
    *,
    file_changes: list[Any],
    include_server_cfg: bool = False,
) -> list[str]:
    """Explicit return-path commit scope — never blanket `git add -A`."""
    selected: list[str] = []
    for change in file_changes:
        if change.change_status == ChangeStatus.DELETED:
            if is_overlay_path(change.path):
                continue
            selected.append(change.path)
            continue
        if is_overlay_path(change.path):
            continue
        if _is_server_cfg_path(change.path) and not include_server_cfg:
            continue
        selected.append(change.path)
    return sorted(dict.fromkeys(selected))


def evaluate_commit_safety(*, staged_files: list[StagedFile], scanner: SecretScannerPort) -> CommitSafetyResult:
    staged_paths = tuple(item.path for item in staged_files)
    findings: list[CommitSafetyFinding] = []
    blocked_paths: list[str] = []
    server_cfg_placeholder_only: bool | None = None

    for staged in staged_files:
        if is_overlay_path(staged.path):
            findings.append(
                CommitSafetyFinding(
                    path=staged.path,
                    line=1,
                    secret_type="overlay_contamination",
                    redacted_preview="[REDACTED]",
                    reason=f"{OVERLAY_FILENAME} must never be committed (gitignored local overlay)",
                )
            )
            blocked_paths.append(staged.path)
            continue

        file_findings = scanner.scan(path=staged.path, content=staged.content)
        for item in file_findings:
            findings.append(
                CommitSafetyFinding(
                    path=item.path,
                    line=item.line,
                    secret_type=item.secret_type,
                    redacted_preview=item.redacted_preview,
                    reason="secret pattern detected in staged content",
                )
            )
            if staged.path not in blocked_paths:
                blocked_paths.append(staged.path)

        if _is_server_cfg_path(staged.path):
            placeholder_only = _server_cfg_is_placeholder_only(staged.content)
            server_cfg_placeholder_only = placeholder_only
            if not placeholder_only:
                if staged.path not in blocked_paths:
                    blocked_paths.append(staged.path)
                if not any(item.path == staged.path and item.secret_type == "pathway2_base_secret" for item in findings):
                    findings.append(
                        CommitSafetyFinding(
                            path=staged.path,
                            line=1,
                            secret_type="pathway2_base_secret",
                            redacted_preview="[REDACTED]",
                            reason="tracked server.cfg must contain placeholders only (CHANGE_ME), not real secrets",
                        )
                    )

    allowed = len(findings) == 0
    return CommitSafetyResult(
        allowed=allowed,
        findings=tuple(findings),
        staged_paths=staged_paths,
        overlay_excluded=True,
        server_cfg_placeholder_only=server_cfg_placeholder_only,
        blocked_paths=tuple(dict.fromkeys(blocked_paths)),
    )


def load_staged_files(*, repo_root: Path, paths: list[str], read_text: Any) -> list[StagedFile]:
    staged: list[StagedFile] = []
    for rel_path in paths:
        absolute = repo_root / rel_path
        if not absolute.is_file():
            staged.append(StagedFile(path=rel_path, content=""))
            continue
        staged.append(StagedFile(path=rel_path, content=read_text(absolute) or ""))
    return staged


def _is_server_cfg_path(path: str) -> bool:
    return Path(path).name == "server.cfg"


def _server_cfg_is_placeholder_only(content: str) -> bool:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lower = stripped.lower()
        if "sv_licensekey" in lower.replace(" ", ""):
            if PLACEHOLDER not in stripped and "changeme" not in lower:
                return False
        if "mysql://" in lower or "postgres://" in lower:
            if PLACEHOLDER not in stripped:
                return False
        if "cfxk_" in lower and PLACEHOLDER not in stripped:
            return False
    return True
