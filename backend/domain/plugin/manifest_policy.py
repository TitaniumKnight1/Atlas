from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.domain.plugin.types import (
    ALL_PLUGIN_CAPABILITIES,
    CONTRIBUTION_CAPABILITY_ALLOWLIST,
    ContributionPoint,
    PluginCapability,
)


MANIFEST_VERSION = "1"
PLUGIN_ID_PATTERN = r"^[a-z][a-z0-9.-]*\.[a-z][a-z0-9.-]*$"


@dataclass(frozen=True, slots=True)
class ManifestValidationIssue:
    code: str
    message: str


@dataclass(slots=True)
class ManifestValidationResult:
    valid: bool
    plugin_id: str | None = None
    requested_capabilities: list[str] = field(default_factory=list)
    contribution_points: list[str] = field(default_factory=list)
    issues: list[ManifestValidationIssue] = field(default_factory=list)


def validate_manifest_payload(payload: dict[str, Any]) -> ManifestValidationResult:
    issues: list[ManifestValidationIssue] = []
    if not isinstance(payload, dict):
        return ManifestValidationResult(valid=False, issues=[ManifestValidationIssue("invalid_type", "Manifest must be a JSON object")])

    manifest_version = payload.get("manifest_version")
    if manifest_version != MANIFEST_VERSION:
        issues.append(ManifestValidationIssue("invalid_manifest_version", f"manifest_version must be '{MANIFEST_VERSION}'"))

    plugin_id = payload.get("plugin_id")
    if not isinstance(plugin_id, str) or not plugin_id:
        issues.append(ManifestValidationIssue("missing_plugin_id", "plugin_id is required"))
        plugin_id = None
    elif not _valid_plugin_id(plugin_id):
        issues.append(ManifestValidationIssue("invalid_plugin_id", "plugin_id must be reverse-DNS (e.g. com.example.plugin)"))

    for field_name in ("name", "version", "author"):
        if not isinstance(payload.get(field_name), str) or not str(payload.get(field_name)).strip():
            issues.append(ManifestValidationIssue(f"missing_{field_name}", f"{field_name} is required"))

    raw_contributions = payload.get("contribution_points", [])
    if not isinstance(raw_contributions, list):
        issues.append(ManifestValidationIssue("invalid_contribution_points", "contribution_points must be an array"))
        raw_contributions = []
    contribution_points: list[str] = []
    for item in raw_contributions:
        if not isinstance(item, str):
            issues.append(ManifestValidationIssue("invalid_contribution_point", "Each contribution point must be a string"))
            continue
        if item not in ContributionPoint._value2member_map_:
            issues.append(ManifestValidationIssue("unknown_contribution_point", f"Unknown contribution point: {item}"))
            continue
        if item in contribution_points:
            issues.append(ManifestValidationIssue("duplicate_contribution_point", f"Duplicate contribution point: {item}"))
            continue
        contribution_points.append(item)

    if not contribution_points:
        issues.append(ManifestValidationIssue("missing_contribution_points", "At least one contribution point is required"))

    raw_capabilities = payload.get("requested_capabilities", [])
    if not isinstance(raw_capabilities, list):
        issues.append(ManifestValidationIssue("invalid_requested_capabilities", "requested_capabilities must be an array"))
        raw_capabilities = []

    if any(item in {"*", "all"} for item in raw_capabilities):
        issues.append(ManifestValidationIssue("wildcard_capability", "Wildcard capability requests are not allowed"))

    requested_capabilities: list[str] = []
    seen: set[str] = set()
    for item in raw_capabilities:
        if not isinstance(item, str):
            issues.append(ManifestValidationIssue("invalid_capability", "Each capability must be a string"))
            continue
        if item in seen:
            issues.append(ManifestValidationIssue("duplicate_capability", f"Duplicate capability: {item}"))
            continue
        seen.add(item)
        try:
            PluginCapability(item)
        except ValueError:
            issues.append(ManifestValidationIssue("unknown_capability", f"Unknown capability: {item}"))
            continue
        requested_capabilities.append(item)

    if not requested_capabilities:
        issues.append(ManifestValidationIssue("missing_capabilities", "At least one requested capability is required"))

    if len(requested_capabilities) >= len(ALL_PLUGIN_CAPABILITIES):
        issues.append(ManifestValidationIssue("over_broad", "Requesting all capabilities is not allowed"))

    if contribution_points and requested_capabilities:
        allowed_for_declared = _allowed_capabilities_for_contributions(contribution_points)
        for capability in requested_capabilities:
            if capability not in allowed_for_declared:
                issues.append(
                    ManifestValidationIssue(
                        "over_broad",
                        f"Capability '{capability}' is not justified by declared contribution points",
                    )
                )

    return ManifestValidationResult(
        valid=not issues,
        plugin_id=plugin_id,
        requested_capabilities=requested_capabilities,
        contribution_points=contribution_points,
        issues=issues,
    )


def _valid_plugin_id(plugin_id: str) -> bool:
    import re

    return bool(re.match(PLUGIN_ID_PATTERN, plugin_id))


def _allowed_capabilities_for_contributions(contribution_points: list[str]) -> set[str]:
    allowed: set[str] = set()
    for contribution in contribution_points:
        allowed.update(cap.value for cap in CONTRIBUTION_CAPABILITY_ALLOWLIST.get(contribution, frozenset()))
    return allowed
