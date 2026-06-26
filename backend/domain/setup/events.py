from __future__ import annotations

from backend.domain.shared_kernel import AggregateRef, DomainEventEnvelope, ProjectId


def artifact_catalog_refreshed(platform: str, channels: list[str], count: int) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ArtifactCatalogRefreshed",
        aggregate_ref=AggregateRef("ArtifactCatalog", platform),
        payload={"platform": platform, "channels": channels, "count": count},
    )


def artifact_version_pinned(project_id: ProjectId, artifact_version_id: str | None, channel: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ArtifactVersionPinned",
        aggregate_ref=AggregateRef("ProjectArtifactPin", str(project_id)),
        project_id=project_id,
        payload={"project_id": str(project_id), "artifact_version_id": artifact_version_id, "channel": channel},
    )


def artifact_installed(project_id: ProjectId, build_number: str, extract_path: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ArtifactInstalled",
        aggregate_ref=AggregateRef("ArtifactVersion", build_number),
        project_id=project_id,
        payload={"project_id": str(project_id), "build_number": build_number, "extract_path": extract_path},
    )


def server_config_written(project_id: ProjectId, server_cfg_path: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ServerConfigWritten",
        aggregate_ref=AggregateRef("ServerConfig", server_cfg_path),
        project_id=project_id,
        payload={"project_id": str(project_id), "server_cfg_path": server_cfg_path},
    )


def setup_run_completed(project_id: ProjectId, setup_run_id: str, status: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="SetupRunCompleted",
        aggregate_ref=AggregateRef("SetupRun", setup_run_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "setup_run_id": setup_run_id, "status": status},
    )


def server_started(project_id: ProjectId, process_run_id: str, pid: int) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ServerStarted",
        aggregate_ref=AggregateRef("ServerProcess", process_run_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "process_run_id": process_run_id, "pid": pid},
    )


def server_stopped(project_id: ProjectId, process_run_id: str, exit_code: int | None) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ServerStopped",
        aggregate_ref=AggregateRef("ServerProcess", process_run_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "process_run_id": process_run_id, "exit_code": exit_code},
    )


def server_crashed(project_id: ProjectId, process_run_id: str, exit_code: int | None) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ServerCrashed",
        aggregate_ref=AggregateRef("ServerProcess", process_run_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "process_run_id": process_run_id, "exit_code": exit_code},
    )
