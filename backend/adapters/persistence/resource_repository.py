from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select

from backend.adapters.persistence.models import (
    ResourceDependencyRecord,
    ResourceHealthSnapshotRecord,
    ResourceInstallSourceRecord,
    ResourceRecord,
    ResourceVersionRecord,
)
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import ProjectScopeRequired, RepositoryContext


class ResourceRepository:
    def __init__(self, context: RepositoryContext) -> None:
        self._session = context.session
        self._project_id = context.project_id

    def upsert_resource(
        self,
        *,
        resource_id: StableIdentifier,
        project_id: ProjectId,
        resource_name: str,
        relative_path: str,
        resource_type: str,
        enabled_state: str,
        startup_order: int | None,
        current_version_id: str | None,
        git_repository_id: str | None,
        created_at: datetime,
        updated_at: datetime,
    ) -> ResourceRecord:
        self._ensure_project_scope(project_id)
        existing = self._session.execute(
            select(ResourceRecord).where(
                ResourceRecord.project_id == str(project_id),
                ResourceRecord.resource_name == resource_name,
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = ResourceRecord(
                resource_id=str(resource_id),
                project_id=str(project_id),
                resource_name=resource_name,
                relative_path=relative_path,
                resource_type=resource_type,
                enabled_state=enabled_state,
                startup_order=startup_order,
                current_version_id=current_version_id,
                git_repository_id=git_repository_id,
                created_at=created_at.isoformat(),
                updated_at=updated_at.isoformat(),
            )
            self._session.add(existing)
            return existing
        existing.relative_path = relative_path
        existing.resource_type = resource_type
        existing.enabled_state = enabled_state
        existing.startup_order = startup_order
        existing.current_version_id = current_version_id
        existing.git_repository_id = git_repository_id
        existing.updated_at = updated_at.isoformat()
        return existing

    def list_resources(self, project_id: ProjectId) -> list[ResourceRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(
                select(ResourceRecord).where(ResourceRecord.project_id == str(project_id)).order_by(ResourceRecord.resource_name)
            ).scalars()
        )

    def get_resource(self, project_id: ProjectId, resource_id: StableIdentifier) -> ResourceRecord | None:
        self._ensure_project_scope(project_id)
        record = self._session.get(ResourceRecord, str(resource_id))
        if record is None or record.project_id != str(project_id):
            return None
        return record

    def get_resource_by_name(self, project_id: ProjectId, resource_name: str) -> ResourceRecord | None:
        self._ensure_project_scope(project_id)
        return self._session.execute(
            select(ResourceRecord).where(
                ResourceRecord.project_id == str(project_id),
                ResourceRecord.resource_name == resource_name,
            )
        ).scalar_one_or_none()

    def add_version(
        self,
        *,
        version_id: StableIdentifier,
        resource_id: str,
        version_label: str | None,
        content_hash: str | None,
        manifest_json: dict[str, Any],
        detected_at: datetime,
        source_ref: str | None = None,
        git_commit_sha: str | None = None,
    ) -> ResourceVersionRecord:
        existing = self._session.execute(
            select(ResourceVersionRecord).where(
                ResourceVersionRecord.resource_id == resource_id,
                ResourceVersionRecord.content_hash == content_hash,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        record = ResourceVersionRecord(
            resource_version_id=str(version_id),
            resource_id=resource_id,
            version_label=version_label,
            git_commit_sha=git_commit_sha,
            source_ref=source_ref,
            content_hash=content_hash,
            manifest_json=manifest_json,
            detected_at=detected_at.isoformat(),
        )
        self._session.add(record)
        return record

    def replace_dependencies(
        self,
        *,
        project_id: ProjectId,
        source_resource_id: str,
        dependencies: list[dict[str, Any]],
        detected_at: datetime,
        name_to_id: dict[str, str],
    ) -> None:
        self._ensure_project_scope(project_id)
        self._session.execute(
            delete(ResourceDependencyRecord).where(ResourceDependencyRecord.source_resource_id == source_resource_id)
        )
        for item in dependencies:
            target_name = item["target_name"]
            self._session.add(
                ResourceDependencyRecord(
                    resource_dependency_id=str(StableIdentifier.new()),
                    project_id=str(project_id),
                    source_resource_id=source_resource_id,
                    target_resource_id=name_to_id.get(target_name),
                    target_name=target_name,
                    dependency_type=item["dependency_type"],
                    declared_in_path=item.get("declared_in_path"),
                    detected_at=detected_at.isoformat(),
                )
            )

    def list_dependencies(self, project_id: ProjectId) -> list[ResourceDependencyRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(select(ResourceDependencyRecord).where(ResourceDependencyRecord.project_id == str(project_id))).scalars()
        )

    def upsert_install_source(
        self,
        *,
        resource_id: str,
        source_type: str,
        source_uri: str | None,
        metadata: dict[str, Any] | None,
        trusted_at: datetime | None,
    ) -> ResourceInstallSourceRecord:
        existing = self._session.execute(
            select(ResourceInstallSourceRecord).where(
                ResourceInstallSourceRecord.resource_id == resource_id,
                ResourceInstallSourceRecord.source_type == source_type,
                ResourceInstallSourceRecord.source_uri == source_uri,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.metadata_json = metadata or {}
            return existing
        record = ResourceInstallSourceRecord(
            resource_install_source_id=str(StableIdentifier.new()),
            resource_id=resource_id,
            source_type=source_type,
            source_uri=source_uri,
            plugin_id=None,
            trusted_at=trusted_at.isoformat() if trusted_at else None,
            metadata_json=metadata or {},
        )
        self._session.add(record)
        return record

    def replace_health_snapshot(
        self,
        *,
        resource_id: str,
        health_status: str,
        sampled_at: datetime,
        details: dict[str, Any],
    ) -> ResourceHealthSnapshotRecord:
        self._session.execute(delete(ResourceHealthSnapshotRecord).where(ResourceHealthSnapshotRecord.resource_id == resource_id))
        record = ResourceHealthSnapshotRecord(
            resource_health_snapshot_id=str(StableIdentifier.new()),
            resource_id=resource_id,
            environment_id=None,
            health_status=health_status,
            server_fps=None,
            cpu_percent=None,
            memory_mb=None,
            sampled_at=sampled_at.isoformat(),
            details_json=details,
        )
        self._session.add(record)
        return record

    def get_latest_health(self, resource_id: str) -> ResourceHealthSnapshotRecord | None:
        return self._session.execute(
            select(ResourceHealthSnapshotRecord)
            .where(ResourceHealthSnapshotRecord.resource_id == resource_id)
            .order_by(ResourceHealthSnapshotRecord.sampled_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _ensure_project_scope(self, project_id: ProjectId) -> None:
        if self._project_id is not None and self._project_id != project_id:
            raise ProjectScopeRequired("Repository project_id does not match requested project_id")
