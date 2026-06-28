from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.adapters.config.validator import unified_diff
from backend.adapters.telemetry.sanitizer import SECRET_RULES

OVERLAY_FILENAME = "server.cfg.local"
OVERLAY_EXAMPLE_FILENAME = "server.cfg.local.example"
EXEC_TRAILER = "exec server.cfg.local"
GITIGNORE_OVERLAY_ENTRY = "server.cfg.local"
PLACEHOLDER = "CHANGE_ME"

EXEC_LINE = re.compile(r"^\s*exec\s+", re.IGNORECASE)
ENDPOINT_UDP = re.compile(r"^\s*endpoint_add_udp\s+", re.IGNORECASE)
ENDPOINT_TCP = re.compile(r"^\s*endpoint_add_tcp\s+", re.IGNORECASE)
LICENSE_LINE = re.compile(r"^\s*sv_licenseKey\s+", re.IGNORECASE)
SET_LINE = re.compile(r"^\s*set\s+(\S+)", re.IGNORECASE)


def find_server_cfg(root: Path) -> Path | None:
    resolved = root.expanduser().resolve()
    for candidate in (resolved / "server.cfg", resolved / "server-data" / "server.cfg"):
        if candidate.is_file():
            return candidate
    return None


def plan_repo_normalization(content: str) -> tuple[str, str, dict[str, Any]]:
    lines = content.splitlines()
    base_lines: list[str] = []
    endpoint_udp_lines: list[str] = []
    endpoint_tcp_lines: list[str] = []
    overlay_secret_lines: list[str] = []
    moved_endpoints: list[str] = []
    secrets_placeholderized = 0

    for line in lines:
        stripped = line.strip()
        if EXEC_LINE.match(line) and OVERLAY_FILENAME in line:
            continue
        if ENDPOINT_UDP.match(line):
            endpoint_udp_lines.append(line)
            moved_endpoints.append(stripped)
            continue
        if ENDPOINT_TCP.match(line):
            endpoint_tcp_lines.append(line)
            moved_endpoints.append(stripped)
            continue
        if _line_needs_secret_placeholder(line):
            placeholder_line = _placeholderize_line(line)
            base_lines.append(placeholder_line)
            overlay_secret_lines.append(placeholder_line)
            secrets_placeholderized += 1
            continue
        base_lines.append(line)

    while base_lines and not base_lines[-1].strip():
        base_lines.pop()

    base_lines.extend(["", "# Pathway 2: local overlay (gitignored) — see ADR-0027", EXEC_TRAILER])

    overlay_parts = [
        "# Atlas Pathway 2 local overlay — gitignored (ADR-0027)",
        "# Complete dev secret substitution in P2-2 before running the server.",
        "",
    ]
    if endpoint_udp_lines or endpoint_tcp_lines:
        overlay_parts.append("# Endpoints moved from server.cfg during adopt normalization")
        overlay_parts.extend(endpoint_udp_lines)
        overlay_parts.extend(endpoint_tcp_lines)
        overlay_parts.append("")
    if overlay_secret_lines:
        overlay_parts.append("# Secret placeholders — set real dev values in P2-2")
        overlay_parts.extend(overlay_secret_lines)
        overlay_parts.append("")
    if not endpoint_udp_lines and not endpoint_tcp_lines and not overlay_secret_lines:
        overlay_parts.append("# No endpoints or inline secrets were moved; P2-2 may add dev values here.")
        overlay_parts.append("")

    overlay_content = "\n".join(overlay_parts).rstrip() + "\n"
    normalized_base = "\n".join(base_lines).rstrip() + "\n"
    meta = {
        "endpoints_moved": moved_endpoints,
        "secrets_placeholderized": secrets_placeholderized,
        "exec_trailer_added": True,
        "ensure_list_preserved": True,
    }
    return normalized_base, overlay_content, meta


def build_overlay_example_content() -> str:
    return (
        "# Copy to server.cfg.local and complete dev secret substitution (P2-2).\n"
        '# Do not commit server.cfg.local — it is gitignored per ADR-0027.\n'
        "\n"
        'endpoint_add_udp "0.0.0.0:30120"\n'
        'endpoint_add_tcp "0.0.0.0:30120"\n'
        f'sv_licenseKey "{PLACEHOLDER}"\n'
        f'set mysql_connection_string "{PLACEHOLDER}"\n'
    )


def scan_inline_secrets(*, path: str, content: str, scanner: Any) -> list[dict[str, Any]]:
    findings = scanner.scan(path=path, content=content)
    return [
        {
            "path": item.path,
            "line": item.line,
            "secret_type": item.secret_type,
            "redacted_preview": item.redacted_preview,
            "severity": item.severity.value if hasattr(item.severity, "value") else str(item.severity),
        }
        for item in findings
    ]


def redact_config_text(content: str) -> str:
    redacted = content
    for _, pattern in SECRET_RULES:
        redacted = pattern.sub(_placeholder_token, redacted)
    return redacted


def redact_unified_diff(diff: str) -> str:
    redacted_lines: list[str] = []
    for line in diff.splitlines(keepends=True):
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            redacted_lines.append(redact_config_text(line))
        else:
            redacted_lines.append(line)
    return "".join(redacted_lines)


def build_normalization_diff(*, current: str, proposed: str, path: str) -> str:
    return redact_unified_diff(unified_diff(current, proposed, path))


def _line_needs_secret_placeholder(line: str) -> bool:
    if LICENSE_LINE.match(line) and PLACEHOLDER not in line:
        return True
    for _, pattern in SECRET_RULES:
        if pattern.search(line):
            return True
    return False


def _placeholderize_line(line: str) -> str:
    if LICENSE_LINE.match(line):
        return f'sv_licenseKey "{PLACEHOLDER}"'
    set_match = SET_LINE.match(line)
    if set_match:
        key = set_match.group(1)
        return f'set {key} "{PLACEHOLDER}"'
    redacted = line
    for _, pattern in SECRET_RULES:
        redacted = pattern.sub(_placeholder_token, redacted)
    return redacted


def _placeholder_token(_match: re.Match[str]) -> str:
    return PLACEHOLDER
