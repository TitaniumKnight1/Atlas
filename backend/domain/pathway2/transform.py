from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.adapters.config.validator import unified_diff
from backend.domain.pathway2.normalization import ENDPOINT_TCP, ENDPOINT_UDP, OVERLAY_FILENAME

TRANSFORM_MARKER_START = "# Atlas P2-3 dev transform (local overlay — non-secret)"
TRANSFORM_MARKER_END = "# End Atlas P2-3 dev transform"

HOSTNAME_LINE = re.compile(r"^\s*sv_hostname\s+", re.IGNORECASE)
MAXCLIENTS_LINE = re.compile(r"^\s*sv_maxclients\s+", re.IGNORECASE)
SET_LINE = re.compile(r"^\s*set\s+(\S+)", re.IGNORECASE)
ONELINE_CONVAR = re.compile(r"^\s*(\S+)\s+(.+)$")


@dataclass(frozen=True, slots=True)
class DevTransformOptions:
    hostname: str = "[DEV] Atlas Local Server"
    max_clients: int = 8
    udp_port: int = 30121
    tcp_port: int = 30121
    dev_convars: dict[str, str] = field(
        default_factory=lambda: {
            "sv_scriptHookAllowed": "1",
            "onesync": "on",
        }
    )


def default_transform_options(*, project_display_name: str | None = None) -> DevTransformOptions:
    hostname = f"[DEV] {project_display_name}" if project_display_name else DevTransformOptions.hostname
    return DevTransformOptions(hostname=hostname)


def plan_dev_config_transform(overlay_content: str, options: DevTransformOptions | None = None) -> tuple[str, dict[str, Any]]:
    opts = options or DevTransformOptions()
    preserved = _strip_prior_transform_and_relocated_lines(overlay_content)
    transform_block = _build_transform_block(opts)
    proposed_parts = preserved.rstrip()
    if proposed_parts:
        proposed_parts += "\n\n"
    proposed_parts += transform_block
    if not proposed_parts.endswith("\n"):
        proposed_parts += "\n"
    meta = {
        "hostname": opts.hostname,
        "max_clients": opts.max_clients,
        "udp_port": opts.udp_port,
        "tcp_port": opts.tcp_port,
        "dev_convars": dict(opts.dev_convars),
        "endpoints_order": "udp_before_tcp",
    }
    return proposed_parts, meta


def build_transform_diff(*, current: str, proposed: str) -> str:
    return unified_diff(current, proposed, OVERLAY_FILENAME)


def _strip_prior_transform_and_relocated_lines(overlay_content: str) -> str:
    lines = overlay_content.splitlines()
    output: list[str] = []
    in_transform = False
    dev_convar_keys = set(DevTransformOptions().dev_convars.keys())
    for line in lines:
        stripped = line.strip()
        if stripped == TRANSFORM_MARKER_START:
            in_transform = True
            continue
        if stripped == TRANSFORM_MARKER_END:
            in_transform = False
            continue
        if in_transform:
            continue
        if ENDPOINT_UDP.match(line) or ENDPOINT_TCP.match(line):
            continue
        if HOSTNAME_LINE.match(line) or MAXCLIENTS_LINE.match(line):
            continue
        set_match = SET_LINE.match(line)
        if set_match and set_match.group(1) in dev_convar_keys:
            continue
        output.append(line)
    while output and not output[-1].strip():
        output.pop()
    return "\n".join(output)


def _build_transform_block(options: DevTransformOptions) -> str:
    lines = [
        TRANSFORM_MARKER_START,
        f'sv_hostname "{_escape_cfg_string(options.hostname)}"',
        f"sv_maxclients {options.max_clients}",
        f'endpoint_add_udp "0.0.0.0:{options.udp_port}"',
        f'endpoint_add_tcp "0.0.0.0:{options.tcp_port}"',
    ]
    for key, value in options.dev_convars.items():
        lines.append(f"set {key} {_quote_if_needed(value)}")
    lines.append(TRANSFORM_MARKER_END)
    return "\n".join(lines)


def _escape_cfg_string(value: str) -> str:
    return value.replace('"', "'")


def _quote_if_needed(value: str) -> str:
    if value.startswith('"') and value.endswith('"'):
        return value
    if value.isdigit() or value in {"on", "off", "true", "false"}:
        return value
    return f'"{value}"'
