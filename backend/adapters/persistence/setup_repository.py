from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from backend.adapters.persistence.models import (
    ArtifactVersionRecord,
    DependencyCheckRecord,
    ProjectArtifactPinRecord,
    SetupRecipeRecord,
    SetupRunRecord,
    SetupRunStepRecord,
    TxAdminInstanceRecord,
)
from backend.domain.setup import ArtifactVersion
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import ProjectScopeRequired, RepositoryContext


class SetupRepository:
    def __init__(self, context: RepositoryContext) -> None:
        self._session = context.session
        self._project_id = context.project_id

    def upsert_artifact_version(self, artifact: ArtifactVersion, discovered_at: datetime) -> ArtifactVersionRecord:
        existing = self._session.execute(
            select(ArtifactVersionRecord).where(
                ArtifactVersionRecord.platform == artifact.platform.value,
                ArtifactVersionRecord.build_number == artifact.build_number,
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = ArtifactVersionRecord(
                artifact_version_id=artifact.artifact_version_id,
                platform=artifact.platform.value,
                channel=artifact.channel.value,
                build_number=artifact.build_number,
                download_url=artifact.download_url,
                sha256=artifact.sha256,
                released_at=artifact.released_at,
                discovered_at=discovered_at.isoformat(),
                metadata_json=artifact.metadata,
            )
            self._session.add(existing)
            return existing
        existing.channel = artifact.channel.value
        existing.download_url = artifact.download_url
        existing.sha256 = artifact.sha256
        existing.released_at = artifact.released_at
        existing.discovered_at = discovered_at.isoformat()
        existing.metadata_json = artifact.metadata
        return existing

    def list_artifact_versions(self, platform: str | None = None, channel: str | None = None) -> list[ArtifactVersionRecord]:
        query = select(ArtifactVersionRecord)
        if platform is not None:
            query = query.where(ArtifactVersionRecord.platform == platform)
        if channel is not None:
            query = query.where(ArtifactVersionRecord.channel == channel)
        return list(self._session.execute(query.order_by(ArtifactVersionRecord.discovered_at.desc())).scalars())

    def get_artifact_version(self, artifact_version_id: str) -> ArtifactVersionRecord | None:
        return self._session.get(ArtifactVersionRecord, artifact_version_id)

    def upsert_artifact_pin(
        self,
        *,
        project_id: ProjectId,
        environment_id: str | None,
        artifact_version_id: str | None,
        channel_preference: str,
        pinned_reason: str | None,
        now: datetime,
    ) -> ProjectArtifactPinRecord:
        self._ensure_project_scope(project_id)
        existing = self._session.execute(
            select(ProjectArtifactPinRecord).where(
                ProjectArtifactPinRecord.project_id == str(project_id),
                ProjectArtifactPinRecord.environment_id == environment_id,
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = ProjectArtifactPinRecord(
                artifact_pin_id=str(StableIdentifier.new()),
                project_id=str(project_id),
                environment_id=environment_id,
                artifact_version_id=artifact_version_id,
                channel_preference=channel_preference,
                pinned_reason=pinned_reason,
                created_at=now.isoformat(),
                updated_at=now.isoformat(),
            )
            self._session.add(existing)
            return existing
        existing.artifact_version_id = artifact_version_id
        existing.channel_preference = channel_preference
        existing.pinned_reason = pinned_reason
        existing.updated_at = now.isoformat()
        return existing

    def get_artifact_pin(self, project_id: ProjectId, environment_id: str | None = None) -> ProjectArtifactPinRecord | None:
        self._ensure_project_scope(project_id)
        return self._session.execute(
            select(ProjectArtifactPinRecord).where(
                ProjectArtifactPinRecord.project_id == str(project_id),
                ProjectArtifactPinRecord.environment_id == environment_id,
            )
        ).scalar_one_or_none()

    def create_setup_run(
        self,
        *,
        setup_run_id: StableIdentifier,
        project_id: ProjectId,
        environment_id: str | None,
        setup_recipe_id: str | None,
        status: str,
        dry_run: bool,
        started_at: datetime | None,
        summary: dict[str, Any] | None,
    ) -> None:
        self._ensure_project_scope(project_id)
        self._session.add(
            SetupRunRecord(
                setup_run_id=str(setup_run_id),
                project_id=str(project_id),
                environment_id=environment_id,
                setup_recipe_id=setup_recipe_id,
                status=status,
                dry_run=1 if dry_run else 0,
                started_at=started_at.isoformat() if started_at else None,
                finished_at=None,
                summary_json=summary or {},
            )
        )

    def finish_setup_run(self, setup_run_id: StableIdentifier, status: str, finished_at: datetime, summary: dict[str, Any]) -> None:
        record = self._session.get(SetupRunRecord, str(setup_run_id))
        if record is None:
            return
        record.status = status
        record.finished_at = finished_at.isoformat()
        record.summary_json = summary

    def add_setup_step(
        self,
        *,
        setup_step_id: StableIdentifier,
        setup_run_id: StableIdentifier,
        step_order: int,
        step_key: str,
        status: str,
        started_at: datetime | None,
        finished_at: datetime | None,
        details: dict[str, Any],
    ) -> None:
        self._session.add(
            SetupRunStepRecord(
                setup_step_id=str(setup_step_id),
                setup_run_id=str(setup_run_id),
                step_order=step_order,
                step_key=step_key,
                status=status,
                started_at=started_at.isoformat() if started_at else None,
                finished_at=finished_at.isoformat() if finished_at else None,
                details_json=details,
            )
        )

    def get_setup_run(self, project_id: ProjectId, setup_run_id: StableIdentifier) -> SetupRunRecord | None:
        self._ensure_project_scope(project_id)
        record = self._session.get(SetupRunRecord, str(setup_run_id))
        if record is None or record.project_id != str(project_id):
            return None
        return record

    def list_setup_steps(self, setup_run_id: StableIdentifier) -> list[SetupRunStepRecord]:
        return list(
            self._session.execute(
                select(SetupRunStepRecord)
                .where(SetupRunStepRecord.setup_run_id == str(setup_run_id))
                .order_by(SetupRunStepRecord.step_order)
            ).scalars()
        )

    def add_dependency_check(
        self,
        *,
        dependency_check_id: StableIdentifier,
        project_id: ProjectId,
        setup_run_id: StableIdentifier | None,
        check_key: str,
        category: str,
        status: str,
        message: str | None,
        details: dict[str, Any] | None,
        checked_at: datetime,
    ) -> None:
        self._ensure_project_scope(project_id)
        self._session.add(
            DependencyCheckRecord(
                dependency_check_id=str(dependency_check_id),
                setup_run_id=str(setup_run_id) if setup_run_id else None,
                project_id=str(project_id),
                check_key=check_key,
                category=category,
                status=status,
                message=message,
                details_json=details or {},
                checked_at=checked_at.isoformat(),
            )
        )

    def list_dependency_checks(self, project_id: ProjectId) -> list[DependencyCheckRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(
                select(DependencyCheckRecord)
                .where(DependencyCheckRecord.project_id == str(project_id))
                .order_by(DependencyCheckRecord.checked_at.desc())
            ).scalars()
        )

    def upsert_txadmin_instance(
        self,
        *,
        project_id: ProjectId,
        txdata_path_id: str | None,
        host: str | None,
        port: int | None,
        detected_version: str | None,
        last_seen_at: datetime,
        metadata: dict[str, Any],
    ) -> TxAdminInstanceRecord:
        self._ensure_project_scope(project_id)
        existing = self._session.execute(
            select(TxAdminInstanceRecord).where(
                TxAdminInstanceRecord.project_id == str(project_id),
                TxAdminInstanceRecord.txdata_path_id == txdata_path_id,
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = TxAdminInstanceRecord(
                txadmin_instance_id=str(StableIdentifier.new()),
                project_id=str(project_id),
                txdata_path_id=txdata_path_id,
                host=host,
                port=port,
                detected_version=detected_version,
                last_seen_at=last_seen_at.isoformat(),
                metadata_json=metadata,
            )
            self._session.add(existing)
            return existing
        existing.host = host
        existing.port = port
        existing.detected_version = detected_version
        existing.last_seen_at = last_seen_at.isoformat()
        existing.metadata_json = metadata
        return existing

    def get_txadmin_instance(self, project_id: ProjectId) -> TxAdminInstanceRecord | None:
        self._ensure_project_scope(project_id)
        return self._session.execute(
            select(TxAdminInstanceRecord).where(TxAdminInstanceRecord.project_id == str(project_id))
        ).scalar_one_or_none()

    def _ensure_project_scope(self, project_id: ProjectId) -> None:
        if self._project_id is not None and self._project_id != project_id:
            raise ProjectScopeRequired("Repository project_id does not match requested project_id")
