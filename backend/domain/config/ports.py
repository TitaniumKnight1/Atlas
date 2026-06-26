from __future__ import annotations

from pathlib import Path
from typing import Protocol

from backend.domain.config.types import SecretFinding, ValidationFinding


class ConfigFilesystemPort(Protocol):
    def read_text(self, path: Path) -> str | None:
        """Read config file text when present."""

    def write_text(self, path: Path, content: str) -> None:
        """Write config file text."""


class ConfigValidationPort(Protocol):
    def validate(self, *, path: str, content: str, config_type: str) -> list[ValidationFinding]:
        """Validate config content without side effects."""


class SecretScannerPort(Protocol):
    def scan(self, *, path: str, content: str) -> list[SecretFinding]:
        """Detect secret-shaped values; never persist raw secrets."""
