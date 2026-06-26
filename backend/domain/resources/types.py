from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ResourceType(StrEnum):
    SCRIPT = "script"
    MAP = "map"
    FRAMEWORK = "framework"
    LIBRARY = "library"
    UNKNOWN = "unknown"


class EnabledState(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class DependencyType(StrEnum):
    REQUIRES = "requires"
    OPTIONAL = "optional"
    CONFLICTS = "conflicts"
    LOADS_AFTER = "loads_after"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"
    UNKNOWN = "unknown"


class FindingType(StrEnum):
    CYCLE = "cycle"
    MISSING_DEPENDENCY = "missing_dependency"
    DUPLICATE_NAME = "duplicate_name"
    DUPLICATE_PROVIDE = "duplicate_provide"
    INVALID_MANIFEST = "invalid_manifest"


class FindingSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ParsedManifest:
    manifest_kind: str
    fx_version: str | None
    games: list[str]
    version: str | None
    dependencies: list[str]
    provides: list[str]
    manifest_valid: bool
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DiscoveredResource:
    resource_name: str
    relative_path: str
    absolute_path: str
    manifest_path: str
    manifest_kind: str
    manifest: ParsedManifest
    content_hash: str | None


@dataclass(frozen=True, slots=True)
class DependencyFinding:
    finding_type: FindingType
    severity: FindingSeverity
    message: str
    nodes: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GraphEdge:
    source: str
    target: str
    dependency_type: str = DependencyType.REQUIRES.value


@dataclass(frozen=True, slots=True)
class DependencyGraphSnapshot:
    nodes: list[str]
    edges: list[GraphEdge]
    provides: dict[str, list[str]]
    findings: list[DependencyFinding]
    topological_order: list[str] | None
    is_healthy: bool
