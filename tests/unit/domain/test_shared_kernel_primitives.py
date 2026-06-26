from __future__ import annotations

import pytest

from backend.domain.shared_kernel import (
    ActorType,
    AggregateRef,
    AuditMetadata,
    DomainEventEnvelope,
    ErrorCode,
    ErrorPayload,
    ProjectId,
    ResultEnvelope,
    Severity,
)


def test_domain_event_envelope_carries_project_scope_and_aggregate_ref() -> None:
    project_id = ProjectId("project-1")
    event = DomainEventEnvelope.create(
        event_type="InfrastructureSmokeRecorded",
        aggregate_ref=AggregateRef("InfrastructureSmoke", "smoke-1"),
        project_id=project_id,
        payload={"value": "ok"},
        audit=AuditMetadata(actor_type=ActorType.SYSTEM, summary="Recorded infrastructure smoke", project_id=project_id),
    )

    record = event.to_record()

    assert record["project_id"] == "project-1"
    assert record["event_type"] == "InfrastructureSmokeRecorded"
    assert record["aggregate_type"] == "InfrastructureSmoke"
    assert record["aggregate_id"] == "smoke-1"
    assert record["payload_json"] == {"value": "ok"}
    assert event.audit is not None
    assert event.audit.actor_type is ActorType.SYSTEM


def test_result_envelope_matches_api_error_shape() -> None:
    success = ResultEnvelope.success({"status": "ok"})
    failure = ResultEnvelope.failure(ErrorPayload(ErrorCode.PROJECT_SCOPE_VIOLATION, "project_id is required"))

    assert success.ok is True
    assert success.data == {"status": "ok"}
    assert success.error is None
    assert success.warnings == []
    assert failure.ok is False
    assert failure.error is not None
    assert failure.error.code is ErrorCode.PROJECT_SCOPE_VIOLATION


def test_invalid_result_envelope_is_rejected() -> None:
    with pytest.raises(ValueError, match="failed ResultEnvelope must include error"):
        ResultEnvelope(ok=False)


def test_severity_values_are_stable_contract_strings() -> None:
    assert Severity.ERROR.value == "error"
