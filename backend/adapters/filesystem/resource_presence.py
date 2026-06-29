from __future__ import annotations

import os
import stat
from pathlib import Path

MANIFEST_FILES = ("fxmanifest.lua", "__resource.lua")
RESOURCE_LIKE_SUFFIXES = (".lua", ".meta")
RESOURCE_LIKE_DIRS = ("stream", "data")


def is_reparse_point(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        if os.name != "nt":
            return False
        attrs = os.lstat(path).st_file_attributes  # type: ignore[attr-defined]
        return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return False


def resolve_resource_dir(path: Path) -> tuple[bool, str]:
    """Return (present, confidence) for a resource directory candidate."""
    try:
        if not path.exists():
            return False, "high"
        resolved = path.resolve(strict=False)
        if not resolved.is_dir():
            return False, "high"
        if is_reparse_point(path):
            return True, "high"
        return True, "high"
    except OSError:
        return False, "low"


def has_manifest(resource_dir: Path) -> bool:
    return any((resource_dir / name).is_file() for name in MANIFEST_FILES)


def has_renamed_manifest_bak(resource_dir: Path) -> bool:
    manifest = resource_dir / "fxmanifest.lua"
    bak = resource_dir / "fxmanifest.lua.bak"
    return not manifest.is_file() and bak.is_file()


def looks_like_resource_dir(resource_dir: Path) -> bool:
    if not resource_dir.is_dir():
        return False
    if has_manifest(resource_dir):
        return True
    if has_renamed_manifest_bak(resource_dir):
        return True
    try:
        for child in resource_dir.iterdir():
            if child.is_file() and child.suffix.lower() in RESOURCE_LIKE_SUFFIXES:
                return True
            if child.is_dir() and child.name.lower() in RESOURCE_LIKE_DIRS:
                return True
    except OSError:
        return False
    return False


def list_resource_roots(resources_root: Path) -> list[Path]:
    """Return FiveM resource root directories (not internal subfolders like data/ or stream/)."""
    resolved_root = resources_root.expanduser().resolve()
    if not resolved_root.is_dir():
        return []
    roots: list[Path] = []
    for entry in sorted(resolved_root.iterdir()):
        if not entry.is_dir() or entry.name.startswith(".") or entry.name == "node_modules":
            continue
        if entry.name.startswith("[") and entry.name.endswith("]"):
            for child in sorted(entry.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    roots.append(child)
        else:
            roots.append(entry)
    return roots


def list_candidate_resource_dirs(resources_root: Path) -> list[Path]:
    """Alias for resource roots — kept for callers expecting the old name."""
    return list_resource_roots(resources_root)
