from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GroupingAction(StrEnum):
    MATCH_EXISTING = "match_existing"
    CREATE_NEW = "create_new"


@dataclass(frozen=True, slots=True)
class ExistingIncidentGroup:
    incident_group_id: str
    fingerprint: str
    occurrence_count: int
    first_seen_at: str
    last_seen_at: str


@dataclass(frozen=True, slots=True)
class GroupingDecision:
    action: GroupingAction
    incident_group_id: str | None = None


def decide_grouping(fingerprint: str, existing_group: ExistingIncidentGroup | None) -> GroupingDecision:
    if existing_group is not None and existing_group.fingerprint == fingerprint:
        return GroupingDecision(action=GroupingAction.MATCH_EXISTING, incident_group_id=existing_group.incident_group_id)
    return GroupingDecision(action=GroupingAction.CREATE_NEW)


def merge_group_timestamps(
    *,
    existing_first_seen_at: str,
    existing_last_seen_at: str,
    existing_count: int,
    occurrence_at: str,
) -> tuple[str, str, int]:
    first_seen = existing_first_seen_at if existing_first_seen_at <= occurrence_at else occurrence_at
    last_seen = existing_last_seen_at if existing_last_seen_at >= occurrence_at else occurrence_at
    return first_seen, last_seen, existing_count + 1
