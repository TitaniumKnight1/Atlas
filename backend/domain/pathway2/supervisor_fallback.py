from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.domain.pathway2.normalization import LICENSE_LINE, SET_LINE
from backend.domain.pathway2.substitution import DEV_SUPPLIED_MARKERS

SECRET_PLUS_SET_KEYS = frozenset({"sv_licenseKey"})
GETCONVAR_LICENSE = re.compile(r"^\s*sv_licenseKey\s+GetConvar\s*\(", re.IGNORECASE)
ONELINE_ONESYNC = re.compile(r"^\s*set\s+onesync\s+(\S+)", re.IGNORECASE)
LICENSE_QUOTED = re.compile(r'^\s*sv_licenseKey\s+"([^"]+)"', re.IGNORECASE)
LICENSE_BARE = re.compile(r"^\s*sv_licenseKey\s+(\S+)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PlusSetOverride:
    key: str
    value: str
    is_secret: bool
    reason: str


def resolve_plus_set_overrides(*, overlay_content: str, base_content: str | None) -> list[PlusSetOverride]:
    """Return only convars that need startup +set injection per ADR-0027."""
    overrides: list[PlusSetOverride] = []
    onesync_value = _overlay_onesync_value(overlay_content)
    if onesync_value is not None:
        overrides.append(
            PlusSetOverride(
                key="onesync",
                value=onesync_value,
                is_secret=False,
                reason="onesync is build-dependent; +set after +exec is the reliable override path (ADR-0027)",
            )
        )
    license_value = _overlay_license_value(overlay_content)
    if license_value and _base_resists_overlay_license(base_content or ""):
        overrides.append(
            PlusSetOverride(
                key="sv_licenseKey",
                value=license_value,
                is_secret=True,
                reason="base sv_licenseKey uses GetConvar; overlay exec cannot replace it — inject via +set",
            )
        )
    return overrides


def build_plus_set_arguments(overrides: list[PlusSetOverride]) -> list[str]:
    args: list[str] = []
    for item in overrides:
        args.extend(["+set", item.key, item.value])
    return args


def mask_launch_arguments(arguments: list[str], *, secret_keys: set[str] | None = None) -> list[str]:
    keys = secret_keys or SECRET_PLUS_SET_KEYS
    masked = list(arguments)
    index = 0
    while index < len(masked):
        if masked[index] == "+set" and index + 2 < len(masked) and masked[index + 1] in keys:
            masked[index + 2] = "[REDACTED]"
            index += 3
            continue
        index += 1
    return masked


def plus_set_preview(overrides: list[PlusSetOverride]) -> list[dict[str, Any]]:
    return [
        {
            "key": item.key,
            "value": "[REDACTED]" if item.is_secret else item.value,
            "is_secret": item.is_secret,
            "reason": item.reason,
        }
        for item in overrides
    ]


def _base_resists_overlay_license(base_content: str) -> bool:
    for line in base_content.splitlines():
        if GETCONVAR_LICENSE.match(line):
            return True
    return False


def _overlay_license_value(overlay_content: str) -> str | None:
    for line in overlay_content.splitlines():
        if not LICENSE_LINE.match(line):
            continue
        quoted = LICENSE_QUOTED.match(line)
        if quoted:
            value = quoted.group(1)
        else:
            bare = LICENSE_BARE.match(line)
            if not bare:
                continue
            value = bare.group(1).strip('"')
        if any(marker in value for marker in DEV_SUPPLIED_MARKERS):
            return None
        if value in {"CHANGE_ME", "changeme"}:
            return None
        return value
    set_match = None
    for line in overlay_content.splitlines():
        match = SET_LINE.match(line)
        if match and match.group(1) == "sv_licenseKey":
            set_match = line
            break
    if set_match is None:
        return None
    parts = set_match.strip().split(maxsplit=2)
    if len(parts) < 3:
        return None
    value = parts[2].strip().strip('"')
    if any(marker in value for marker in DEV_SUPPLIED_MARKERS) or value == "CHANGE_ME":
        return None
    return value


def _overlay_onesync_value(overlay_content: str) -> str | None:
    for line in overlay_content.splitlines():
        match = ONELINE_ONESYNC.match(line)
        if match:
            return match.group(1).strip('"')
    return None
