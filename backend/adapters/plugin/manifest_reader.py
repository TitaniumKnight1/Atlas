from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ManifestReadError(RuntimeError):
    pass


def read_manifest_file(path: Path) -> dict[str, Any]:
    """Declarative manifest read — json.loads only; never imports plugin code."""
    if not path.exists():
        raise ManifestReadError(f"Manifest file not found: {path}")
    if path.suffix.lower() not in {".json"}:
        raise ManifestReadError("Only JSON manifests are supported in M9a")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ManifestReadError(f"Invalid JSON manifest: {error}") from error
    if not isinstance(payload, dict):
        raise ManifestReadError("Manifest root must be a JSON object")
    return payload


def parse_manifest_dict(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ManifestReadError("Manifest must be a JSON object")
    return dict(payload)
