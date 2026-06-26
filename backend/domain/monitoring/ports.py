from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from backend.domain.monitoring.types import CollectedMetricSample
from backend.domain.shared_kernel import ProjectId


@dataclass(frozen=True, slots=True)
class CollectorContext:
    project_id: ProjectId
    sampled_at: datetime
    process_run_id: str | None
    project_root: Path | None


class MetricCollectorPort(Protocol):
    collector_id: str
    source_type: str

    def collect(self, context: CollectorContext) -> list[CollectedMetricSample]:
        """Sample one collector source and return zero or more metric points."""
