from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from backend.adapters.persistence import PluginRepository, ProjectRepository
from backend.adapters.plugin.manifest_reader import ManifestReadError, parse_manifest_dict, read_manifest_file
from backend.application.commands import CommandPreview, RiskLevel
from backend.application.commands.recorder import CommandAuditRecorder
from backend.domain.plugin import (
    ConsentModel,
    HONEST_TRUST_WARNING,
    ManifestValidationResult,
    PluginRegistrationStatus,
    PluginTrustStatus,
    capability_granted,
    capability_revoked,
    plugin_disabled,
    plugin_registered,
    validate_manifest_payload,
)
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier


class PluginApplicationError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class PluginApplicationService:
    def __init__(self, *, container: Any, clock: Callable[[], datetime] | None = None) -> None:
        self._container = container
        self._clock = clock or (lambda: datetime.now(UTC))
        self._recorder = CommandAuditRecorder()

    def get_global_settings(self) -> dict[str, Any]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            enabled = PluginRepository(RepositoryContext(session=session)).get_global_enabled()
        return {"global_enabled": enabled, "consent_model": ConsentModel.INTEGRITY_NOT_SANDBOX.value, "trust_warning": HONEST_TRUST_WARNING}

    def set_global_enabled(self, *, enabled: bool) -> dict[str, Any]:
        now = self._clock()
        with self._container.create_unit_of_work() as uow:
            uow.begin()
            payload = uow.repository(PluginRepository).set_global_enabled(enabled=enabled, updated_at=now)
            uow.commit()
        return {"global_enabled": payload["enabled"]}

    def validate_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        result = validate_manifest_payload(parse_manifest_dict(manifest))
        return _validation_data(result)

    def validate_manifest_file(self, manifest_path: str) -> dict[str, Any]:
        payload = read_manifest_file(Path(manifest_path))
        return self.validate_manifest(payload)

    def list_plugins(self) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            records = PluginRepository(RepositoryContext(session=session)).list_registrations()
        return [_registration_data(record) for record in records]

    def get_plugin(self, plugin_id: str) -> dict[str, Any]:
        record = self._require_registration(plugin_id)
        return _registration_data(record)

    def register_plugin(
        self,
        manifest: dict[str, Any],
        *,
        source_ref: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        validation = validate_manifest_payload(parse_manifest_dict(manifest))
        if not validation.valid or validation.plugin_id is None:
            raise PluginApplicationError(ErrorCode.VALIDATION_FAILED, _format_issues(validation))
        existing = self._get_by_key(validation.plugin_id)
        if existing is not None:
            if idempotency_key and existing.manifest_json == manifest:
                return _registration_data(existing)
            raise PluginApplicationError(ErrorCode.CONFLICT, f"Plugin already registered: {validation.plugin_id}")
        now = self._clock()
        plugin_id = StableIdentifier.new()
        with self._container.create_unit_of_work() as uow:
            uow.begin()
            repository = uow.repository(PluginRepository)
            record = repository.create_registration(
                plugin_id=plugin_id,
                plugin_key=validation.plugin_id,
                name=str(manifest["name"]),
                version=str(manifest["version"]),
                author=str(manifest["author"]),
                manifest_json=manifest,
                source_ref=source_ref,
                contribution_points=validation.contribution_points,
                requested_capabilities=validation.requested_capabilities,
                registration_status=PluginRegistrationStatus.REGISTERED.value,
                trust_status=PluginTrustStatus.PENDING_CONSENT.value,
                is_enabled=False,
                registered_at=now,
            )
            uow.collect_event(plugin_registered(validation.plugin_id, version=str(manifest["version"])))
            uow.commit()
        return _registration_data(record)

    def set_plugin_enabled(self, plugin_id: str, *, enabled: bool) -> dict[str, Any]:
        record = self._require_registration(plugin_id)
        if enabled and not self._has_any_active_grant(record.plugin_id):
            raise PluginApplicationError(ErrorCode.PRECONDITION_FAILED, "Cannot enable plugin without granted capabilities")
        if enabled and not self.get_global_settings()["global_enabled"]:
            raise PluginApplicationError(ErrorCode.PRECONDITION_FAILED, "Global plugin kill switch is disabled")
        now = self._clock()
        with self._container.create_unit_of_work() as uow:
            uow.begin()
            repository = uow.repository(PluginRepository)
            registration = repository.get_registration(plugin_id)
            assert registration is not None
            repository.update_registration_state(
                registration,
                registration_status=PluginRegistrationStatus.REGISTERED.value if enabled else PluginRegistrationStatus.DISABLED.value,
                is_enabled=enabled,
                updated_at=now,
            )
            if not enabled:
                uow.collect_event(plugin_disabled(registration.plugin_key, reason="user_disabled"))
            uow.commit()
        return _registration_data(registration)

    def list_capabilities(self, plugin_id: str, project_id: ProjectId) -> dict[str, Any]:
        record = self._require_registration(plugin_id)
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            repository = PluginRepository(RepositoryContext(session=session, project_id=project_id))
            grants = repository.list_active_grants(plugin_id, project_id)
            trust = repository.latest_trust_record(plugin_id, project_id)
        return {
            "plugin_id": plugin_id,
            "plugin_key": record.plugin_key,
            "project_id": str(project_id),
            "requested_capabilities": record.requested_capabilities_json,
            "granted_capabilities": [grant.capability for grant in grants],
            "trust_status": record.trust_status,
            "consent_model": trust.consent_model if trust else None,
            "trust_acknowledgment": trust.trust_acknowledgment_json if trust else None,
        }

    def grant_capabilities(
        self,
        plugin_id: str,
        project_id: ProjectId,
        *,
        capabilities: list[str],
        trust_acknowledgment: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        record = self._require_registration(plugin_id)
        requested = set(record.requested_capabilities_json)
        for capability in capabilities:
            if capability not in requested:
                raise PluginApplicationError(
                    ErrorCode.VALIDATION_FAILED,
                    f"Capability '{capability}' was not requested in manifest",
                )
        if not trust_acknowledgment.get("user_confirmed"):
            raise PluginApplicationError(ErrorCode.PERMISSION_DENIED, "Explicit user confirmation is required")
        if trust_acknowledgment.get("consent_model") != ConsentModel.INTEGRITY_NOT_SANDBOX.value:
            raise PluginApplicationError(ErrorCode.VALIDATION_FAILED, "Unsupported consent model")
        if trust_acknowledgment.get("acknowledged_warning") != HONEST_TRUST_WARNING:
            raise PluginApplicationError(ErrorCode.VALIDATION_FAILED, "Trust warning must be acknowledged verbatim")
        now = self._clock()
        preview = CommandPreview(
            command_type="plugin.grant_capabilities",
            summary=f"Grant capabilities to plugin {record.plugin_key}",
            preview={"plugin_id": plugin_id, "capabilities": capabilities, "project_id": str(project_id)},
            risk_level=RiskLevel.HIGH,
        )
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            uow.repository(ProjectRepository).get_project(project_id) or self._missing_project(project_id)
            repository = uow.repository(PluginRepository)
            granted: list[str] = []
            for capability in capabilities:
                existing = repository.get_active_grant(plugin_id, capability, project_id)
                if existing is not None:
                    granted.append(capability)
                    continue
                repository.create_grant(
                    grant_id=StableIdentifier.new(),
                    plugin_id=plugin_id,
                    project_id=project_id,
                    capability=capability,
                    scope_json=None,
                    granted_at=now,
                )
                granted.append(capability)
                uow.collect_event(capability_granted(record.plugin_key, capability=capability, project_id=project_id))
            repository.create_trust_record(
                trust_record_id=StableIdentifier.new(),
                plugin_id=plugin_id,
                project_id=project_id,
                consent_model=ConsentModel.INTEGRITY_NOT_SANDBOX.value,
                trust_acknowledgment=trust_acknowledgment,
                granted_capabilities=granted,
                consented_at=now,
            )
            registration = repository.get_registration(plugin_id)
            assert registration is not None
            repository.update_registration_state(
                registration,
                trust_status=PluginTrustStatus.CONSENTED.value,
                updated_at=now,
            )
            self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="plugin",
                entity_id=plugin_id,
                summary=preview.summary,
                result={"granted_capabilities": granted},
                events=[],
                undo_plan=None,
                idempotency_key=idempotency_key,
            )
            uow.commit()
        return self.list_capabilities(plugin_id, project_id)

    def revoke_capability(
        self,
        plugin_id: str,
        project_id: ProjectId,
        *,
        capability: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        record = self._require_registration(plugin_id)
        now = self._clock()
        preview = CommandPreview(
            command_type="plugin.revoke_capability",
            summary=f"Revoke capability {capability} from plugin {record.plugin_key}",
            preview={"plugin_id": plugin_id, "capability": capability, "project_id": str(project_id)},
            risk_level=RiskLevel.MEDIUM,
        )
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(PluginRepository)
            grant = repository.get_active_grant(plugin_id, capability, project_id)
            if grant is None:
                uow.rollback()
                raise PluginApplicationError(ErrorCode.NOT_FOUND, f"Active grant not found: {capability}")
            repository.revoke_grant(grant, revoked_at=now)
            uow.session.flush()
            registration = repository.get_registration(plugin_id)
            assert registration is not None
            if not repository.list_active_grants(plugin_id, project_id):
                repository.update_registration_state(
                    registration,
                    trust_status=PluginTrustStatus.REVOKED.value,
                    is_enabled=False,
                    registration_status=PluginRegistrationStatus.DISABLED.value,
                    updated_at=now,
                )
            self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="plugin",
                entity_id=plugin_id,
                summary=preview.summary,
                result={"revoked_capability": capability},
                events=[],
                undo_plan=None,
                idempotency_key=idempotency_key,
            )
            uow.collect_event(capability_revoked(record.plugin_key, capability=capability, project_id=project_id))
            uow.commit()
        return self.list_capabilities(plugin_id, project_id)

    def _require_registration(self, plugin_id: str):
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            record = PluginRepository(RepositoryContext(session=session)).get_registration(plugin_id)
        if record is None:
            raise PluginApplicationError(ErrorCode.NOT_FOUND, f"Plugin not found: {plugin_id}")
        return record

    def _get_by_key(self, plugin_key: str):
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            return PluginRepository(RepositoryContext(session=session)).get_registration_by_key(plugin_key)

    def _has_any_active_grant(self, plugin_id: str) -> bool:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            grants = PluginRepository(RepositoryContext(session=session)).list_active_grants(plugin_id)
        return bool(grants)

    def _missing_project(self, project_id: ProjectId) -> None:
        raise PluginApplicationError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")


def _validation_data(result: ManifestValidationResult) -> dict[str, Any]:
    return {
        "valid": result.valid,
        "plugin_id": result.plugin_id,
        "requested_capabilities": result.requested_capabilities,
        "contribution_points": result.contribution_points,
        "issues": [{"code": issue.code, "message": issue.message} for issue in result.issues],
    }


def _registration_data(record: Any) -> dict[str, Any]:
    return {
        "plugin_id": record.plugin_id,
        "plugin_key": record.plugin_key,
        "name": record.name,
        "version": record.version,
        "author": record.author,
        "source_ref": record.source_ref,
        "contribution_points": record.contribution_points_json,
        "requested_capabilities": record.requested_capabilities_json,
        "registration_status": record.registration_status,
        "trust_status": record.trust_status,
        "is_enabled": bool(record.is_enabled),
        "registered_at": record.registered_at,
        "updated_at": record.updated_at,
    }


def _format_issues(result: ManifestValidationResult) -> str:
    return "; ".join(issue.message for issue in result.issues) or "Manifest validation failed"
