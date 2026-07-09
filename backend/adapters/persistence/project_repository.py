from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update

from backend.adapters.persistence.models import (
    EnvironmentProfileRecord,
    ProjectPathRecord,
    ProjectRecord,
    ProjectSettingRecord,
    ProjectTemplateRecord,
    WorkspaceTrustDecisionRecord,
)
from backend.domain.project import ProjectStatus, SettingValueType
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import ProjectScopeRequired, RepositoryContext


class ProjectRepository:
    def __init__(self, context: RepositoryContext) -> None:
        self._session = context.session
        self._project_id = context.project_id

    def slug_exists(self, slug: str) -> bool:
        return self._session.execute(select(ProjectRecord.project_id).where(ProjectRecord.slug == slug)).first() is not None

    def find_project_by_slug(self, slug: str) -> ProjectRecord | None:
        return self._session.execute(select(ProjectRecord).where(ProjectRecord.slug == slug)).scalar_one_or_none()

    def get_root_path(self, project_id: ProjectId) -> str | None:
        record = self._session.execute(
            select(ProjectPathRecord).where(
                ProjectPathRecord.project_id == str(project_id),
                ProjectPathRecord.path_role == "root",
            )
        ).scalar_one_or_none()
        return record.absolute_path if record is not None else None

    def reset_project_for_reimport(
        self,
        project_id: ProjectId,
        *,
        display_name: str,
        updated_at: datetime,
    ) -> None:
        self._ensure_project_scope(project_id)
        scoped_id = str(project_id)
        self._session.execute(delete(ProjectSettingRecord).where(ProjectSettingRecord.project_id == scoped_id))
        self._session.execute(delete(EnvironmentProfileRecord).where(EnvironmentProfileRecord.project_id == scoped_id))
        self._session.execute(delete(ProjectPathRecord).where(ProjectPathRecord.project_id == scoped_id))
        self._session.execute(
            update(ProjectRecord)
            .where(ProjectRecord.project_id == scoped_id)
            .values(
                display_name=display_name,
                status=ProjectStatus.ACTIVE.value,
                updated_at=updated_at.isoformat(),
                last_opened_at=None,
                default_environment_id=None,
            )
        )

    def add_project(
        self,
        *,
        project_id: ProjectId,
        slug: str,
        display_name: str,
        description: str | None,
        created_at: datetime,
    ) -> None:
        timestamp = created_at.isoformat()
        self._session.add(
            ProjectRecord(
                project_id=str(project_id),
                slug=slug,
                display_name=display_name,
                description=description,
                status=ProjectStatus.ACTIVE.value,
                default_environment_id=None,
                created_at=timestamp,
                updated_at=timestamp,
                last_opened_at=None,
            )
        )

    def add_path(
        self,
        *,
        project_id: ProjectId,
        role: str,
        absolute_path: str,
        exists: bool,
        created_at: datetime,
    ) -> None:
        self._session.add(
            ProjectPathRecord(
                project_path_id=str(StableIdentifier.new()),
                project_id=str(project_id),
                path_role=role,
                absolute_path=absolute_path,
                exists_last_checked=1 if exists else 0,
                content_hash=None,
                last_checked_at=created_at.isoformat(),
                created_at=created_at.isoformat(),
            )
        )

    def get_project(self, project_id: ProjectId | None = None) -> ProjectRecord | None:
        scoped_project_id = project_id or self._require_project_id()
        return self._session.get(ProjectRecord, str(scoped_project_id))

    def list_projects(self) -> list[ProjectRecord]:
        return list(self._session.execute(select(ProjectRecord).order_by(ProjectRecord.updated_at.desc())).scalars())

    def list_paths(self, project_id: ProjectId | None = None, role: str | None = None) -> list[ProjectPathRecord]:
        scoped_project_id = project_id or self._require_project_id()
        query = select(ProjectPathRecord).where(ProjectPathRecord.project_id == str(scoped_project_id))
        if role is not None:
            query = query.where(ProjectPathRecord.path_role == role)
        return list(self._session.execute(query.order_by(ProjectPathRecord.path_role)).scalars())

    def mark_opened(self, project_id: ProjectId, opened_at: datetime) -> None:
        self._ensure_project_scope(project_id)
        self._session.execute(
            update(ProjectRecord)
            .where(ProjectRecord.project_id == str(project_id))
            .values(last_opened_at=opened_at.isoformat(), updated_at=opened_at.isoformat())
        )

    def archive_project(self, project_id: ProjectId, archived_at: datetime) -> None:
        self._ensure_project_scope(project_id)
        self._session.execute(
            update(ProjectRecord)
            .where(ProjectRecord.project_id == str(project_id))
            .values(status=ProjectStatus.ARCHIVED.value, updated_at=archived_at.isoformat())
        )

    def delete_project_metadata(self, project_id: ProjectId) -> None:
        self._ensure_project_scope(project_id)
        self._session.execute(delete(ProjectPathRecord).where(ProjectPathRecord.project_id == str(project_id)))
        self._session.execute(delete(EnvironmentProfileRecord).where(EnvironmentProfileRecord.project_id == str(project_id)))
        self._session.execute(delete(ProjectSettingRecord).where(ProjectSettingRecord.project_id == str(project_id)))
        self._session.execute(delete(WorkspaceTrustDecisionRecord).where(WorkspaceTrustDecisionRecord.project_id == str(project_id)))
        self._session.execute(delete(ProjectRecord).where(ProjectRecord.project_id == str(project_id)))

    def upsert_settings(
        self,
        *,
        project_id: ProjectId,
        patch: dict[str, Any],
        updated_at: datetime,
        updated_by: str | None = None,
    ) -> list[str]:
        self._ensure_project_scope(project_id)
        changed_keys: list[str] = []
        for key, value in patch.items():
            existing = self._session.execute(
                select(ProjectSettingRecord).where(
                    ProjectSettingRecord.project_id == str(project_id),
                    ProjectSettingRecord.setting_key == key,
                )
            ).scalar_one_or_none()
            if existing is None:
                self._session.add(
                    ProjectSettingRecord(
                        project_setting_id=str(StableIdentifier.new()),
                        project_id=str(project_id),
                        setting_key=key,
                        value_json=value,
                        value_type=_value_type(value).value,
                        updated_at=updated_at.isoformat(),
                        updated_by=updated_by,
                    )
                )
            else:
                existing.value_json = value
                existing.value_type = _value_type(value).value
                existing.updated_at = updated_at.isoformat()
                existing.updated_by = updated_by
            changed_keys.append(key)
        return changed_keys

    def list_settings(self, project_id: ProjectId | None = None, keys: list[str] | None = None) -> list[ProjectSettingRecord]:
        scoped_project_id = project_id or self._require_project_id()
        query = select(ProjectSettingRecord).where(ProjectSettingRecord.project_id == str(scoped_project_id))
        if keys:
            query = query.where(ProjectSettingRecord.setting_key.in_(keys))
        return list(self._session.execute(query.order_by(ProjectSettingRecord.setting_key)).scalars())

    def create_environment(
        self,
        *,
        project_id: ProjectId,
        environment_id: StableIdentifier,
        name: str,
        display_name: str,
        artifact_channel: str | None,
        settings: dict[str, Any],
        is_default: bool,
        created_at: datetime,
    ) -> None:
        self._ensure_project_scope(project_id)
        timestamp = created_at.isoformat()
        self._session.add(
            EnvironmentProfileRecord(
                environment_id=str(environment_id),
                project_id=str(project_id),
                name=name,
                display_name=display_name,
                artifact_channel=artifact_channel,
                settings_json=settings,
                is_default=1 if is_default else 0,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        if is_default:
            self._session.execute(
                update(ProjectRecord)
                .where(ProjectRecord.project_id == str(project_id))
                .values(default_environment_id=str(environment_id), updated_at=timestamp)
            )

    def list_environments(self, project_id: ProjectId | None = None) -> list[EnvironmentProfileRecord]:
        scoped_project_id = project_id or self._require_project_id()
        return list(
            self._session.execute(
                select(EnvironmentProfileRecord)
                .where(EnvironmentProfileRecord.project_id == str(scoped_project_id))
                .order_by(EnvironmentProfileRecord.name)
            ).scalars()
        )

    def update_environment(
        self,
        *,
        project_id: ProjectId,
        environment_id: StableIdentifier,
        display_name: str | None,
        artifact_channel: str | None,
        settings: dict[str, Any] | None,
        updated_at: datetime,
    ) -> EnvironmentProfileRecord | None:
        self._ensure_project_scope(project_id)
        profile = self._session.get(EnvironmentProfileRecord, str(environment_id))
        if profile is None or profile.project_id != str(project_id):
            return None
        if display_name is not None:
            profile.display_name = display_name
        if artifact_channel is not None:
            profile.artifact_channel = artifact_channel
        if settings is not None:
            profile.settings_json = settings
        profile.updated_at = updated_at.isoformat()
        return profile

    def upsert_trust_decision(
        self,
        *,
        project_id: ProjectId,
        trust_decision_id: StableIdentifier,
        trust_state: str,
        scope: str,
        scope_ref: str | None,
        reason: str | None,
        decided_at: datetime,
        decided_by: str | None,
    ) -> StableIdentifier:
        self._ensure_project_scope(project_id)
        existing = self._session.execute(
            select(WorkspaceTrustDecisionRecord).where(
                WorkspaceTrustDecisionRecord.project_id == str(project_id),
                WorkspaceTrustDecisionRecord.scope == scope,
                WorkspaceTrustDecisionRecord.scope_ref == scope_ref,
            )
        ).scalar_one_or_none()
        if existing is None:
            self._session.add(
                WorkspaceTrustDecisionRecord(
                    trust_decision_id=str(trust_decision_id),
                    project_id=str(project_id),
                    trust_state=trust_state,
                    scope=scope,
                    scope_ref=scope_ref,
                    reason=reason,
                    decided_at=decided_at.isoformat(),
                    decided_by=decided_by,
                )
            )
            return trust_decision_id
        existing.trust_state = trust_state
        existing.reason = reason
        existing.decided_at = decided_at.isoformat()
        existing.decided_by = decided_by
        return StableIdentifier(existing.trust_decision_id)

    def list_trust_decisions(self, project_id: ProjectId | None = None) -> list[WorkspaceTrustDecisionRecord]:
        scoped_project_id = project_id or self._require_project_id()
        return list(
            self._session.execute(
                select(WorkspaceTrustDecisionRecord)
                .where(WorkspaceTrustDecisionRecord.project_id == str(scoped_project_id))
                .order_by(WorkspaceTrustDecisionRecord.scope)
            ).scalars()
        )

    def list_templates(self) -> list[ProjectTemplateRecord]:
        return list(self._session.execute(select(ProjectTemplateRecord).order_by(ProjectTemplateRecord.display_name)).scalars())

    def _require_project_id(self) -> ProjectId:
        if self._project_id is None:
            raise ProjectScopeRequired("Project repository operation requires project_id")
        return self._project_id

    def _ensure_project_scope(self, project_id: ProjectId) -> None:
        if self._project_id is not None and self._project_id != project_id:
            raise ProjectScopeRequired("Repository project_id does not match requested project_id")


def _value_type(value: object) -> SettingValueType:
    from backend.domain.project import value_type_for

    return value_type_for(value)
