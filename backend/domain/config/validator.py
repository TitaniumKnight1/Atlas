from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from backend.adapters.filesystem.resource_presence import has_manifest, has_renamed_manifest_bak
from backend.domain.config.resource_index import ResourceIndex, build_resource_index
from backend.domain.config.structural import (
    AutoFixKind,
    ConfigFinding,
    ConfigFindingRemediation,
    ConfigFindingType,
    StructuralValidationResult,
    StructuralValidationStatus,
)
from backend.domain.config.types import FindingSeverity, SecretFinding
from backend.domain.config.server_cfg_discovery import EXEC_LINE, find_server_cfg

ENSURE_PATTERN = re.compile(r"^\s*(?:ensure|start)\s+([^\s#;]+)", re.IGNORECASE)
ABSOLUTE_PATH_PATTERN = re.compile(
    r'(?:"([^"]*(?:[A-Za-z]:[\\/]|/home/|/Users/)[^"]*)"|\'([^\']*(?:[A-Za-z]:[\\/]|/home/|/Users/)[^\']*)\')'
)
SET_LINE = re.compile(r"^\s*(?:set|setr|sets)\s+", re.IGNORECASE)
MANIFEST_FILES = ("fxmanifest.lua", "__resource.lua")


class ConfigFileReader(Protocol):
    def read_text(self, path: Path) -> str | None: ...


@dataclass(frozen=True, slots=True)
class ParsedEnsureRef:
    path: str
    line: int
    resource_name: str
    raw_line: str


class ConfigValidator:
    """Structural FiveM config validation: dangling refs, manifests, paths, secrets."""

    def validate(
        self,
        *,
        root: Path,
        server_cfg_path: Path,
        server_cfg_content: str,
        resource_index: ResourceIndex,
        secret_findings: list[SecretFinding],
        exec_contents: dict[str, str] | None = None,
    ) -> list[ConfigFinding]:
        rel_cfg = _relative_path(root, server_cfg_path)
        findings: list[ConfigFinding] = []
        ensured_names = self._collect_ensure_refs(
            root=root,
            primary_path=server_cfg_path,
            primary_rel=rel_cfg,
            primary_content=server_cfg_content,
            exec_contents=exec_contents or {},
        )
        findings.extend(self._find_dangling_refs(ensured_names, resource_index))
        findings.extend(self._find_missing_manifests(root, resource_index, ensured_names))
        findings.extend(self._find_absolute_paths(rel_cfg, server_cfg_content))
        for exec_rel, content in (exec_contents or {}).items():
            findings.extend(self._find_absolute_paths(exec_rel, content))
        findings.extend(self._map_secret_findings(secret_findings))
        return findings

    def _collect_ensure_refs(
        self,
        *,
        root: Path,
        primary_path: Path,
        primary_rel: str,
        primary_content: str,
        exec_contents: dict[str, str],
    ) -> dict[str, list[ParsedEnsureRef]]:
        refs: dict[str, list[ParsedEnsureRef]] = {}
        visited_exec: set[str] = set()
        queue: list[tuple[str, str]] = [(primary_rel, primary_content)]
        while queue:
            rel_path, content = queue.pop(0)
            for ref in _parse_ensure_lines(rel_path, content):
                refs.setdefault(ref.resource_name, []).append(ref)
            for exec_target in _parse_exec_targets(rel_path, content):
                if exec_target in visited_exec:
                    continue
                visited_exec.add(exec_target)
                if exec_target in exec_contents:
                    queue.append((exec_target, exec_contents[exec_target]))
        return refs

    def _find_dangling_refs(
        self,
        ensured: dict[str, list[ParsedEnsureRef]],
        resource_index: ResourceIndex,
    ) -> list[ConfigFinding]:
        findings: list[ConfigFinding] = []
        for resource_name, refs in sorted(ensured.items()):
            present, confidence = resource_index.resource_present(resource_name)
            if present:
                continue
            ref = refs[0]
            severity = FindingSeverity.WARNING.value if confidence == "low" else FindingSeverity.ERROR.value
            message = (
                f'ensure/start references "{resource_name}" but no matching directory was found under resources/ '
                f"(junction-aware scan, confidence: {confidence})."
            )
            findings.append(
                ConfigFinding(
                    finding_id=_finding_id(ConfigFindingType.DANGLING_RESOURCE_REFERENCE, ref.path, ref.line, resource_name),
                    type=ConfigFindingType.DANGLING_RESOURCE_REFERENCE,
                    severity=severity,
                    path=ref.path,
                    line=ref.line,
                    message=message,
                    remediation=ConfigFindingRemediation(
                        auto_fix_available=True,
                        auto_fix_kind=AutoFixKind.COMMENT_OUT_ENSURE.value,
                        requires_confirmation=False,
                    ),
                    context={
                        "offending_line": ref.raw_line,
                        "resource_name": resource_name,
                        "expected": "A resource directory under resources/ with fxmanifest.lua, or remove/comment this line.",
                        "confidence": confidence,
                    },
                )
            )
        return findings

    def _find_missing_manifests(
        self,
        root: Path,
        resource_index: ResourceIndex,
        ensured: dict[str, list[ParsedEnsureRef]],
    ) -> list[ConfigFinding]:
        findings: list[ConfigFinding] = []
        seen: set[str] = set()
        for path in resource_index.missing_manifest_dirs():
            rel = _relative_path(root, path)
            if rel in seen:
                continue
            seen.add(rel)
            resource_name = path.name
            ensured_here = resource_name in ensured
            bak = has_renamed_manifest_bak(path)
            if bak:
                detail = f"{resource_name} has fxmanifest.lua.bak but no active fxmanifest.lua or __resource.lua."
            elif ensured_here:
                detail = f"{resource_name} is ensured in server.cfg but has no fxmanifest.lua or __resource.lua."
            else:
                detail = f"{resource_name} looks like a resource directory but has no fxmanifest.lua or __resource.lua."
            findings.append(
                ConfigFinding(
                    finding_id=_finding_id(ConfigFindingType.MISSING_MANIFEST, rel, None, resource_name),
                    type=ConfigFindingType.MISSING_MANIFEST,
                    severity=FindingSeverity.ERROR.value if ensured_here else FindingSeverity.WARNING.value,
                    path=rel,
                    line=None,
                    message=detail,
                    remediation=ConfigFindingRemediation(auto_fix_available=False),
                    context={
                        "resource_name": resource_name,
                        "offending_line": None,
                        "expected": "fxmanifest.lua or __resource.lua in the resource directory.",
                        "manifest_bak_present": bak,
                        "ensured_in_cfg": ensured_here,
                    },
                )
            )
        return findings

    def _find_absolute_paths(self, rel_path: str, content: str) -> list[ConfigFinding]:
        findings: list[ConfigFinding] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            if not SET_LINE.match(line):
                continue
            match = ABSOLUTE_PATH_PATTERN.search(line)
            if match is None:
                continue
            absolute_value = match.group(1) or match.group(2) or ""
            findings.append(
                ConfigFinding(
                    finding_id=_finding_id(ConfigFindingType.ABSOLUTE_PATH, rel_path, line_number, absolute_value[:32]),
                    type=ConfigFindingType.ABSOLUTE_PATH,
                    severity=FindingSeverity.WARNING.value,
                    path=rel_path,
                    line=line_number,
                    message="Config value contains an absolute dev path that may not port to another machine.",
                    remediation=ConfigFindingRemediation(
                        auto_fix_available=True,
                        auto_fix_kind=AutoFixKind.REWRITE_ABSOLUTE_PATH.value,
                        requires_confirmation=True,
                    ),
                    context={
                        "offending_line": line.strip(),
                        "absolute_path": absolute_value,
                        "expected": "A relative or portable path (e.g. relative to server root).",
                    },
                )
            )
        return findings

    def _map_secret_findings(self, secret_findings: list[SecretFinding]) -> list[ConfigFinding]:
        findings: list[ConfigFinding] = []
        for item in secret_findings:
            line = item.line or 0
            secret_type = item.secret_type
            findings.append(
                ConfigFinding(
                    finding_id=_finding_id(ConfigFindingType.INLINE_SECRET, item.path or "unknown", line, secret_type),
                    type=ConfigFindingType.INLINE_SECRET,
                    severity=item.severity.value if hasattr(item.severity, "value") else str(item.severity),
                    path=item.path or "unknown",
                    line=item.line,
                    message=f"Inline secret detected ({secret_type}); value is masked in Atlas.",
                    remediation=ConfigFindingRemediation(auto_fix_available=False),
                    context={
                        "secret_type": secret_type,
                        "redacted_preview": item.redacted_preview,
                        "offending_line": f"[a secret of type {secret_type} at line {line}]",
                    },
                )
            )
        return findings


def run_config_validation(
    *,
    root: Path,
    filesystem: ConfigFileReader,
    secret_scanner: Any,
) -> StructuralValidationResult:
    resolved = root.expanduser().resolve()
    server_cfg = find_server_cfg(resolved)
    if server_cfg is None:
        return StructuralValidationResult(
            status=StructuralValidationStatus.SKIPPED_NO_SERVER_CFG,
            findings=(),
            server_cfg_path=None,
        )
    rel_cfg = _relative_path(resolved, server_cfg)
    content = filesystem.read_text(server_cfg) or ""
    resources_root = resolved / "resources"
    resource_index = build_resource_index(resources_root)
    exec_contents = _load_exec_fragments(root=resolved, server_cfg=server_cfg, content=content, filesystem=filesystem)
    secret_findings: list[SecretFinding] = []
    for rel_path, fragment in [(rel_cfg, content), *exec_contents.items()]:
        secret_findings.extend(secret_scanner.scan(path=rel_path, content=fragment))
    validator = ConfigValidator()
    findings = validator.validate(
        root=resolved,
        server_cfg_path=server_cfg,
        server_cfg_content=content,
        resource_index=resource_index,
        secret_findings=secret_findings,
        exec_contents=exec_contents,
    )
    return StructuralValidationResult(
        status=StructuralValidationStatus.VALIDATED,
        findings=tuple(findings),
        server_cfg_path=rel_cfg,
    )


def _load_exec_fragments(
    *,
    root: Path,
    server_cfg: Path,
    content: str,
    filesystem: ConfigFileReader,
) -> dict[str, str]:
    fragments: dict[str, str] = {}
    visited: set[str] = set()
    queue: list[tuple[Path, str]] = [(server_cfg, content)]
    while queue:
        cfg_path, cfg_content = queue.pop(0)
        rel = _relative_path(root, cfg_path)
        for exec_target in _parse_exec_targets(rel, cfg_content):
            if exec_target in visited:
                continue
            visited.add(exec_target)
            absolute = (cfg_path.parent / exec_target).resolve()
            if not absolute.is_file():
                continue
            try:
                relative = _relative_path(root, absolute)
            except ValueError:
                relative = exec_target.replace("\\", "/")
            fragment = filesystem.read_text(absolute) or ""
            fragments[relative] = fragment
            queue.append((absolute, fragment))
    return fragments


def _parse_ensure_lines(rel_path: str, content: str) -> list[ParsedEnsureRef]:
    refs: list[ParsedEnsureRef] = []
    for line_number, raw in enumerate(content.splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        match = ENSURE_PATTERN.match(stripped)
        if match is None:
            continue
        token = match.group(1).strip().strip('"').strip("'")
        if token:
            refs.append(ParsedEnsureRef(path=rel_path, line=line_number, resource_name=token, raw_line=raw.rstrip()))
    return refs


def _parse_exec_targets(rel_path: str, content: str) -> list[str]:
    targets: list[str] = []
    cfg_parent = Path(rel_path).parent
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        if not EXEC_LINE.match(line):
            continue
        remainder = stripped.split(None, 1)
        if len(remainder) < 2:
            continue
        target = remainder[1].strip().strip('"').strip("'")
        if not target:
            continue
        normalized = str((cfg_parent / target)).replace("\\", "/")
        targets.append(normalized)
    return targets


def _relative_path(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def _finding_id(finding_type: ConfigFindingType, path: str, line: int | None, key: str) -> str:
    payload = f"{finding_type.value}:{path}:{line}:{key}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
