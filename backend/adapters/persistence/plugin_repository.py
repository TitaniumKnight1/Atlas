from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from backend.adapters.persistence.models import (
    PluginCapabilityGrantRecord,
    PluginRegistrationRecord,
    PluginSettingRecord,
    PluginTrustRecord,
)
from backend.domain.plugin.types import PluginSettingKey
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import ProjectScopeRequired, RepositoryContext


class PluginRepository:
    def __init__(self, context: RepositoryContext) -> None:
        self._session = context.session
        self._project_id = context.project_id

    def get_global_enabled(self) -> bool:
        record = self._session.get(PluginSettingRecord, PluginSettingKey.GLOBAL_ENABLED.value)
        if record is None:
            return True
        return bool(record.setting_value_json.get("enabled", True))

    def set_global_enabled(self, *, enabled: bool, updated_at: datetime) -> dict[str, Any]:
        record = self._session.get(PluginSettingRecord, PluginSettingKey.GLOBAL_ENABLED.value)
        payload = {"enabled": enabled}
        if record is None:
            self._session.add(
                PluginSettingRecord(
                    setting_key=PluginSettingKey.GLOBAL_ENABLED.value,
                    setting_value_json=payload,
                    updated_at=updated_at.isoformat(),
                )
            )
        else:
            record.setting_value_json = payload
            record.updated_at = updated_at.isoformat()
        return payload

    def create_registration(
        self,
        *,
        plugin_id: StableIdentifier,
        plugin_key: str,
        name: str,
        version: str,
        author: str,
        manifest_json: dict[str, Any],
        source_ref: str | None,
        contribution_points: list[str],
        requested_capabilities: list[str],
        registration_status: str,
        trust_status: str,
        is_enabled: bool,
        registered_at: datetime,
    ) -> PluginRegistrationRecord:
        record = PluginRegistrationRecord(
            plugin_id=str(plugin_id),
            plugin_key=plugin_key,
            name=name,
            version=version,
            author=author,
            manifest_json=manifest_json,
            source_ref=source_ref,
            contribution_points_json=contribution_points,
            requested_capabilities_json=requested_capabilities,
            registration_status=registration_status,
            trust_status=trust_status,
            is_enabled=1 if is_enabled else 0,
            registered_at=registered_at.isoformat(),
            updated_at=registered_at.isoformat(),
        )
        self._session.add(record)
        return record

    def get_registration(self, plugin_id: str) -> PluginRegistrationRecord | None:
        return self._session.get(PluginRegistrationRecord, plugin_id)

    def get_registration_by_key(self, plugin_key: str) -> PluginRegistrationRecord | None:
        return self._session.execute(
            select(PluginRegistrationRecord).where(PluginRegistrationRecord.plugin_key == plugin_key)
        ).scalar_one_or_none()

    def list_registrations(self) -> list[PluginRegistrationRecord]:
        return list(
            self._session.execute(select(PluginRegistrationRecord).order_by(PluginRegistrationRecord.name)).scalars()
        )

    def update_registration_state(
        self,
        record: PluginRegistrationRecord,
        *,
        registration_status: str | None = None,
        trust_status: str | None = None,
        is_enabled: bool | None = None,
        updated_at: datetime,
    ) -> None:
        if registration_status is not None:
            record.registration_status = registration_status
        if trust_status is not None:
            record.trust_status = trust_status
        if is_enabled is not None:
            record.is_enabled = 1 if is_enabled else 0
        record.updated_at = updated_at.isoformat()

    def create_grant(
        self,
        *,
        grant_id: StableIdentifier,
        plugin_id: str,
        project_id: ProjectId | None,
        capability: str,
        scope_json: dict[str, Any] | None,
        granted_at: datetime,
    ) -> PluginCapabilityGrantRecord:
        if project_id is not None:
            self._ensure_project_scope(project_id)
        record = PluginCapabilityGrantRecord(
            grant_id=str(grant_id),
            plugin_id=plugin_id,
            project_id=str(project_id) if project_id else None,
            capability=capability,
            scope_json=scope_json or {},
            is_active=1,
            granted_at=granted_at.isoformat(),
            revoked_at=None,
        )
        self._session.add(record)
        return record

    def get_active_grant(self, plugin_id: str, capability: str, project_id: ProjectId | None) -> PluginCapabilityGrantRecord | None:
        if project_id is not None:
            self._ensure_project_scope(project_id)
        return self._session.execute(
            select(PluginCapabilityGrantRecord).where(
                PluginCapabilityGrantRecord.plugin_id == plugin_id,
                PluginCapabilityGrantRecord.capability == capability,
                PluginCapabilityGrantRecord.project_id == (str(project_id) if project_id else None),
                PluginCapabilityGrantRecord.is_active == 1,
            )
        ).scalar_one_or_none()

    def list_active_grants(self, plugin_id: str, project_id: ProjectId | None = None) -> list[PluginCapabilityGrantRecord]:
        if project_id is not None:
            self._ensure_project_scope(project_id)
        query = select(PluginCapabilityGrantRecord).where(
            PluginCapabilityGrantRecord.plugin_id == plugin_id,
            PluginCapabilityGrantRecord.is_active == 1,
        )
        if project_id is not None:
            query = query.where(PluginCapabilityGrantRecord.project_id == str(project_id))
        return list(self._session.execute(query.order_by(PluginCapabilityGrantRecord.granted_at.desc())).scalars())

    def revoke_grant(self, grant: PluginCapabilityGrantRecord, *, revoked_at: datetime) -> None:
        grant.is_active = 0
        grant.revoked_at = revoked_at.isoformat()

    def create_trust_record(
        self,
        *,
        trust_record_id: StableIdentifier,
        plugin_id: str,
        project_id: ProjectId | None,
        consent_model: str,
        trust_acknowledgment: dict[str, Any],
        granted_capabilities: list[str],
        consented_at: datetime,
    ) -> PluginTrustRecord:
        if project_id is not None:
            self._ensure_project_scope(project_id)
        record = PluginTrustRecord(
            trust_record_id=str(trust_record_id),
            plugin_id=plugin_id,
            project_id=str(project_id) if project_id else None,
            consent_model=consent_model,
            trust_acknowledgment_json=trust_acknowledgment,
            granted_capabilities_json=granted_capabilities,
            consented_at=consented_at.isoformat(),
            revoked_at=None,
        )
        self._session.add(record)
        return record

    def latest_trust_record(self, plugin_id: str, project_id: ProjectId | None = None) -> PluginTrustRecord | None:
        if project_id is not None:
            self._ensure_project_scope(project_id)
        query = select(PluginTrustRecord).where(PluginTrustRecord.plugin_id == plugin_id)
        if project_id is not None:
            query = query.where(PluginTrustRecord.project_id == str(project_id))
        else:
            query = query.where(PluginTrustRecord.project_id.is_(None))
        return self._session.execute(query.order_by(PluginTrustRecord.consented_at.desc())).scalars().first()

    def _ensure_project_scope(self, project_id: ProjectId) -> None:
        if self._project_id is not None and self._project_id != project_id:
            raise ProjectScopeRequired("Repository project scope does not match requested project_id")
