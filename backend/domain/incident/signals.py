from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FingerprintSignals:
    """Stack-trace-independent signals available from M7a snapshots."""

    category: str
    severity: str
    source_type: str
    exit_code: int | None
    exception_type: str | None
    normalized_message: str
    log_lines: tuple[str, ...]
    resource_hint: str | None = None
