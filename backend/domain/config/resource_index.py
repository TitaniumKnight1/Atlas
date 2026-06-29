from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.adapters.filesystem.resource_presence import (
    has_manifest,
    has_renamed_manifest_bak,
    list_candidate_resource_dirs,
    looks_like_resource_dir,
    resolve_resource_dir,
)


@dataclass
class ResourceIndex:
    resources_root: Path
    by_name: dict[str, list[Path]] = field(default_factory=dict)
    bracket_dirs: set[str] = field(default_factory=set)
    candidate_dirs: list[Path] = field(default_factory=list)

    def resource_present(self, token: str) -> tuple[bool, str]:
        if token.startswith("[") and token.endswith("]"):
            bracket_path = self.resources_root / token
            present, confidence = resolve_resource_dir(bracket_path)
            return present, confidence
        paths = self.by_name.get(token, [])
        if paths:
            for path in paths:
                present, confidence = resolve_resource_dir(path)
                if present:
                    return True, confidence
            return False, "high"
        return False, "high"

    def missing_manifest_dirs(self) -> list[Path]:
        missing: list[Path] = []
        for path in self.candidate_dirs:
            if has_manifest(path):
                continue
            if looks_like_resource_dir(path):
                missing.append(path)
        return missing


def build_resource_index(resources_root: Path) -> ResourceIndex:
    resolved = resources_root.expanduser().resolve()
    index = ResourceIndex(resources_root=resolved)
    if not resolved.is_dir():
        return index
    for child in sorted(resolved.iterdir()):
        if child.is_dir() and child.name.startswith("[") and child.name.endswith("]"):
            index.bracket_dirs.add(child.name)
    for path in list_candidate_resource_dirs(resolved):
        index.candidate_dirs.append(path)
        name = path.name
        index.by_name.setdefault(name, []).append(path)
    return index
