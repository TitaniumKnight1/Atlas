from __future__ import annotations

from backend.adapters.telemetry.sanitizer import SECRET_RULES
from backend.domain.config.structural import ConfigFinding, ConfigFindingType


def _redact_prompt_text(content: str) -> str:
    redacted = content
    for _, pattern in SECRET_RULES:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def build_fix_prompt(finding: ConfigFinding, *, server_root_hint: str | None = None) -> str:
    lines = [
        "You are fixing a FiveM server configuration issue.",
        "",
        f"Issue: {finding.type.value} ({finding.severity})",
        f"File: {finding.path}" + (f", line {finding.line}" if finding.line else ""),
    ]
    if finding.type == ConfigFindingType.INLINE_SECRET:
        secret_type = finding.context.get("secret_type", "secret")
        line_ref = finding.line or "?"
        lines.append(f'Offending line: [a secret of type {secret_type} at line {line_ref}]')
        lines.append(
            "Task: Move this value to server.cfg.local / environment substitution; "
            "replace with CHANGE_ME placeholder in tracked config. Never commit real secrets."
        )
    else:
        offending = finding.context.get("offending_line")
        if offending:
            lines.append(f"Offending line: {offending}")
        expected = finding.context.get("expected")
        if expected:
            lines.append(f"Expected: {expected}")
        if finding.type == ConfigFindingType.DANGLING_RESOURCE_REFERENCE:
            resource = finding.context.get("resource_name", "?")
            lines.append(f'Context: resources/ has no directory named "{resource}" (junction-aware scan).')
            lines.append(
                "Task: Either comment out this ensure/start line or locate/add the missing resource. "
                "Do not invent resource contents."
            )
        elif finding.type == ConfigFindingType.MISSING_MANIFEST:
            resource = finding.context.get("resource_name", "?")
            if finding.context.get("manifest_bak_present"):
                lines.append(f"Context: {resource} has fxmanifest.lua.bak but no active manifest.")
            lines.append(
                f"Task: Generate a correct fxmanifest.lua for {resource} based on its actual files. "
                "Do not guess dependencies — inspect the directory first."
            )
        elif finding.type == ConfigFindingType.ABSOLUTE_PATH:
            if server_root_hint:
                lines.append(f"Server root: {server_root_hint}")
            lines.append(
                "Task: Rewrite this value to a portable relative path (relative to server root where possible). "
                "Confirm the path still resolves on the target machine."
            )
    return _redact_prompt_text("\n".join(lines))


def build_all_issues_prompt(findings: list[ConfigFinding], *, server_root_hint: str | None = None) -> str:
    if not findings:
        return "No structural configuration issues were detected."
    header = [
        "You are fixing structural issues in a FiveM server repository.",
        f"Total issues: {len(findings)}",
    ]
    if server_root_hint:
        header.append(f"Server root: {server_root_hint}")
    header.append("")
    header.append("Fix each issue below. Secrets are masked — never paste or invent secret values.")
    header.append("")
    sections = ["\n".join(header)]
    for index, finding in enumerate(findings, start=1):
        sections.append(f"--- Issue {index} ---")
        sections.append(build_fix_prompt(finding, server_root_hint=server_root_hint))
        sections.append("")
    return _redact_prompt_text("\n".join(sections).rstrip() + "\n")
