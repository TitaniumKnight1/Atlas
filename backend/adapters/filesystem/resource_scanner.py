from __future__ import annotations

import hashlib
import re
from pathlib import Path

from backend.domain.resources.manifest_parser import parse_manifest
from backend.domain.resources.types import DiscoveredResource, ResourceType


MANIFEST_FILES = ("fxmanifest.lua", "__resource.lua")
ENSURE_PATTERN = re.compile(r"^\s*(?:ensure|start)\s+([^\s#;]+)", re.IGNORECASE)


class LocalResourceScanner:
    def __init__(self, filesystem: object) -> None:
        self._filesystem = filesystem

    def discover_resources(self, roots: list[Path]) -> list[DiscoveredResource]:
        discovered: list[DiscoveredResource] = []
        seen: set[str] = set()
        for root in roots:
            base = root.expanduser().resolve()
            if not base.exists() or not base.is_dir():
                continue
            for child in sorted(base.iterdir()):
                if not child.is_dir():
                    continue
                manifest = _find_manifest(child)
                if manifest is None:
                    continue
                relative = str(child.relative_to(base)).replace("\\", "/")
                if relative in seen:
                    continue
                seen.add(relative)
                content = self._filesystem.read_text(manifest) or ""
                parsed = parse_manifest(content, manifest_kind=manifest.name)
                discovered.append(
                    DiscoveredResource(
                        resource_name=child.name,
                        relative_path=relative,
                        absolute_path=str(child.resolve()),
                        manifest_path=str(manifest),
                        manifest_kind=manifest.name,
                        manifest=parsed,
                        content_hash=_content_hash(content),
                    )
                )
        return discovered

    def parse_server_cfg_enabled(self, server_cfg_content: str | None) -> dict[str, bool]:
        enabled: dict[str, bool] = {}
        if not server_cfg_content:
            return enabled
        for line in server_cfg_content.splitlines():
            match = ENSURE_PATTERN.match(line.strip())
            if match is None:
                continue
            token = match.group(1).strip().strip('"').strip("'")
            if token:
                enabled[token] = True
        return enabled


def _find_manifest(resource_dir: Path) -> Path | None:
    for name in MANIFEST_FILES:
        candidate = resource_dir / name
        if candidate.exists():
            return candidate
    return None


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def infer_resource_type(manifest: object, resource_name: str) -> str:
    lowered = resource_name.lower()
    if any(token in lowered for token in ("map", "ymap", "mlo")):
        return ResourceType.MAP.value
    if any(token in lowered for token in ("core", "framework", "esx", "qb")):
        return ResourceType.FRAMEWORK.value
    if any(token in lowered for token in ("lib", "library", "ox_")):
        return ResourceType.LIBRARY.value
    return ResourceType.SCRIPT.value
