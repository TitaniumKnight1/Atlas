from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from re import sub


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    MISSING = "missing"
    DELETED = "deleted"


class ProjectPathRole(StrEnum):
    ROOT = "root"
    SERVER_DATA = "server_data"
    RESOURCES = "resources"
    TXDATA = "txdata"
    ARTIFACTS = "artifacts"
    BACKUPS = "backups"
    LOGS = "logs"


class TrustState(StrEnum):
    TRUSTED = "trusted"
    RESTRICTED = "restricted"
    REVOKED = "revoked"


class TrustScope(StrEnum):
    PROJECT = "project"
    PLUGIN = "plugin"
    PATH = "path"


class SettingValueType(StrEnum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"


@dataclass(frozen=True, slots=True)
class DetectedProjectPath:
    role: ProjectPathRole
    absolute_path: str
    exists: bool


def slug_from_path(path: Path) -> str:
    slug = sub(r"[^a-z0-9]+", "-", path.name.lower()).strip("-")
    return slug or "project"


def value_type_for(value: object) -> SettingValueType:
    if isinstance(value, bool):
        return SettingValueType.BOOLEAN
    if isinstance(value, int | float):
        return SettingValueType.NUMBER
    if isinstance(value, str):
        return SettingValueType.STRING
    if isinstance(value, list):
        return SettingValueType.ARRAY
    return SettingValueType.OBJECT
