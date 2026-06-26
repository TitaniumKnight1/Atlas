from __future__ import annotations

from typing import Any

from backend.domain.incident.signals import FingerprintSignals
from backend.domain.incident.types import ContextSnapshotType, IncidentCategory, IncidentSeverity, IncidentSourceType


def signals_from_assembled(
    *,
    message: str,
    context_snapshots: list[dict[str, Any]],
    stack_trace: dict[str, Any] | None,
) -> FingerprintSignals:
    by_type = {item["context_type"]: item.get("snapshot_json") or {} for item in context_snapshots}
    runtime = by_type.get(ContextSnapshotType.RUNTIME.value, {})
    logs = by_type.get(ContextSnapshotType.LOGS.value, {})
    log_lines = tuple((logs.get("stderr_tail") or []) + (logs.get("stdout_tail") or []))
    return FingerprintSignals(
        category=IncidentCategory.CRASH.value,
        severity=IncidentSeverity.FATAL.value,
        source_type=IncidentSourceType.PROCESS.value,
        exit_code=runtime.get("exit_code"),
        exception_type=(stack_trace or {}).get("exception_type"),
        normalized_message=message,
        log_lines=log_lines,
    )


def signals_from_timeline(
    *,
    message: str,
    context_snapshots: list[dict[str, Any]],
    stack_trace: dict[str, Any] | None,
) -> FingerprintSignals:
    return signals_from_assembled(message=message, context_snapshots=context_snapshots, stack_trace=stack_trace)
