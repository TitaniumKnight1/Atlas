from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass(frozen=True, slots=True)
class RetentionDecision:
    backup_run_id: str
    action: str
    reason: str


def evaluate_retention(
    runs: list[dict[str, Any]],
    *,
    policy: dict[str, Any],
    now: datetime,
) -> list[RetentionDecision]:
    """Decide which succeeded backups to prune. Never silently drop the last backup."""
    keep_count = int(policy.get("keep_count", 5))
    keep_days = int(policy.get("keep_days", 30))
    allow_prune_last = bool(policy.get("allow_prune_last", False))
    succeeded = [run for run in runs if run.get("status") == "succeeded"]
    if not succeeded:
        return []
    succeeded_sorted = sorted(succeeded, key=lambda item: item["started_at"], reverse=True)
    decisions: list[RetentionDecision] = []
    cutoff = now - timedelta(days=keep_days)
    for index, run in enumerate(succeeded_sorted):
        started = datetime.fromisoformat(run["started_at"])
        over_count = index >= keep_count
        over_age = started < cutoff
        if not over_count and not over_age:
            continue
        if len(succeeded_sorted) == 1 and not allow_prune_last:
            decisions.append(RetentionDecision(run["backup_run_id"], "skipped", "last_backup_protected"))
            continue
        if len(succeeded_sorted) - len([d for d in decisions if d.action == "prune"]) <= 1 and not allow_prune_last:
            decisions.append(RetentionDecision(run["backup_run_id"], "skipped", "would_remove_last_backup"))
            continue
        reason = []
        if over_count:
            reason.append("keep_count_exceeded")
        if over_age:
            reason.append("keep_days_exceeded")
        decisions.append(RetentionDecision(run["backup_run_id"], "prune", "+".join(reason)))
    return decisions
