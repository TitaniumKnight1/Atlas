from __future__ import annotations

import re

from backend.adapters.telemetry.sanitizer import SECRET_RULES
from backend.domain.config import FindingSeverity, SecretFinding

REDACTION = "[REDACTED]"


class LocalConfigSecretScanner:
    """Detect secret-shaped config values for local UI masking only."""

    def scan(self, *, path: str, content: str) -> list[SecretFinding]:
        findings: list[SecretFinding] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            for secret_type, pattern in SECRET_RULES:
                match = pattern.search(line)
                if match is None:
                    continue
                preview = _redacted_preview(match.group(0))
                findings.append(
                    SecretFinding(
                        detector_id="local_config_secret_scanner",
                        severity=FindingSeverity.WARNING,
                        path=path,
                        line=line_number,
                        redacted_preview=preview,
                        secret_type=secret_type,
                    )
                )
        return findings


def _redacted_preview(value: str) -> str:
    if len(value) <= 8:
        return REDACTION
    return f"{value[:4]}...{REDACTION}"
