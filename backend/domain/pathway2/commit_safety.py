from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from backend.domain.git import ChangeStatus
from backend.domain.pathway2.normalization import (
    GITIGNORE_OVERLAY_ENTRY,
    OVERLAY_EXAMPLE_FILENAME,
    OVERLAY_FILENAME,
    PLACEHOLDER,
)

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
            f"Paths in safe commit set: {len(self.staged_paths)}",
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
            "manual_push_message": (
                "Return-path commit uses explicit paths only — never blanket git add. "
                f"Tracked server.cfg may be included when it contains placeholders only; "
                f"{OVERLAY_FILENAME} is gitignored and is never committed. "
                "Commit locally when your changes are ready, then push with your git tool — Atlas does not push."
            ),
        }

    @staticmethod
    def _normalized_path(path: str) -> str:
        return Path(path).name.replace("\\", "/")


def is_overlay_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized.endswith(f"/{OVERLAY_FILENAME}") or normalized == OVERLAY_FILENAME or normalized.endswith(f"/{GITIGNORE_OVERLAY_ENTRY}")


RETURN_PATH_UNTRACKED_ALLOWLIST = frozenset({".gitignore", OVERLAY_EXAMPLE_FILENAME})


def build_normalization_path_candidates(*, server_cfg_rel: str | None) -> set[str]:
    """Paths Atlas may touch during adopt normalization — never the whole imported tree."""
    candidates: set[str] = {".gitignore"}
    if not server_cfg_rel:
        return candidates
    rel = server_cfg_rel.replace("\\", "/")
    candidates.add(rel)
    candidates.add(str(Path(rel).with_name(OVERLAY_EXAMPLE_FILENAME)).replace("\\", "/"))
    return candidates


def classify_commit_scope(*, paths: list[str], normalization_paths: set[str]) -> dict[str, Any]:
    normalization = [
        path
        for path in paths
        if path in normalization_paths
        or Path(path).name in RETURN_PATH_UNTRACKED_ALLOWLIST
        or _is_server_cfg_path(path)
    ]
    dev_changes = [path for path in paths if path not in normalization]
    return {
        "normalization_paths": normalization,
        "dev_change_paths": dev_changes,
        "normalization_only": len(dev_changes) == 0,
        "total_paths": len(paths),
    }


def select_default_return_commit_paths(
    *,
    file_changes: list[Any],
    include_server_cfg: bool = False,
    normalization_paths: set[str] | None = None,
) -> list[str]:
    """Explicit return-path commit scope — never blanket `git add -A`.

    Untracked files from a freshly imported tree (no git baseline) are excluded except
    Atlas normalization artifacts. Tracked modifications/deletions are dev-facing changes.
    """
    normalization_paths = normalization_paths or set()
    selected: list[str] = []
    for change in file_changes:
        path = change.path.replace("\\", "/")
        if change.change_status == ChangeStatus.UNTRACKED:
            if path in normalization_paths or Path(path).name in RETURN_PATH_UNTRACKED_ALLOWLIST:
                selected.append(path)
            elif include_server_cfg and _is_server_cfg_path(path):
                selected.append(path)
            continue
        if change.change_status == ChangeStatus.DELETED:
            if is_overlay_path(path):
                continue
            selected.append(path)
            continue
        if is_overlay_path(path):
            continue
        if _is_server_cfg_path(path) and not include_server_cfg:
            continue
        selected.append(path)
    return sorted(dict.fromkeys(selected))


def server_cfg_eligible_for_return_commit(
    *,
    file_changes: list[Any],
    project_root: Path,
    read_text: Any,
    normalization_paths: set[str] | None = None,
) -> bool:
    """Include tracked server.cfg in return-path scope only when placeholders-only on disk."""
    from backend.domain.git import ChangeStatus

    normalization_paths = normalization_paths or set()
    for change in file_changes:
        path = change.path.replace("\\", "/")
        if not _is_server_cfg_path(path) and path not in normalization_paths:
            continue
        if change.change_status == ChangeStatus.DELETED:
            continue
        absolute = project_root / path
        if not absolute.is_file():
            continue
        content = read_text(absolute) or ""
        if _server_cfg_is_placeholder_only(content):
            return True
    return False


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
