from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from backend.adapters.persistence import PluginRepository, ProjectRepository
from backend.application.plugin.service import PluginApplicationError
from backend.domain.plugin.events import (
    plugin_contribution_failed,
    plugin_contribution_invoked,
    plugin_contribution_registered,
)
from backend.domain.plugin.types import CONTRIBUTION_REQUIRED_CAPABILITIES, ContributionPoint
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier


class PluginContributionService:
    """Registers and invokes plugin contributions through the M9b subprocess host."""

    def __init__(self, *, container: Any, clock: Callable[[], datetime] | None = None) -> None:
        self._container = container
        self._clock = clock or (lambda: datetime.now(UTC))

    def register_manifest_contributions(self, plugin_id: str, project_id: ProjectId) -> dict[str, Any]:
        now = self._clock()
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            uow.repository(ProjectRepository).get_project(project_id) or self._missing_project(project_id)
            repository = uow.repository(PluginRepository)
            registration = repository.get_registration(plugin_id)
            if registration is None:
                uow.rollback()
                raise PluginApplicationError(ErrorCode.NOT_FOUND, f"Plugin not found: {plugin_id}")
            if not repository.get_global_enabled() or not registration.is_enabled:
                uow.rollback()
                return {"registered": [], "skipped": [{"reason": "plugin_disabled_or_global_kill_switch"}]}
            descriptors = _manifest_contributions(registration.manifest_json)
            registered: list[dict[str, Any]] = []
            skipped: list[dict[str, Any]] = []
            for descriptor in descriptors:
                point = str(descriptor.get("contribution_point") or "")
                identifier = str(descriptor.get("identifier") or "")
                if point not in ContributionPoint._value2member_map_ or not identifier:
                    skipped.append({"descriptor": descriptor, "reason": "invalid_descriptor"})
                    continue
                if point not in (registration.contribution_points_json or []):
                    skipped.append({"descriptor": descriptor, "reason": "contribution_point_not_declared"})
                    continue
                required = sorted(cap.value for cap in CONTRIBUTION_REQUIRED_CAPABILITIES.get(point, frozenset()))
                if not required:
                    skipped.append({"descriptor": descriptor, "reason": "no_required_capability_mapping"})
                    continue
                missing = [capability for capability in required if repository.get_active_grant(plugin_id, capability, project_id) is None]
                if missing:
                    skipped.append({"descriptor": descriptor, "reason": "missing_capability", "missing_capabilities": missing})
                    continue
                contribution = repository.create_or_update_contribution(
                    contribution_id=StableIdentifier.new(),
                    plugin_id=plugin_id,
                    project_id=project_id,
                    contribution_point=point,
                    identifier=identifier,
                    required_capability=required[0],
                    descriptor_json=descriptor,
                    is_enabled=True,
                    registered_at=now,
                )
                uow.collect_event(
                    plugin_contribution_registered(
                        registration.plugin_key,
                        contribution_id=contribution.contribution_id,
                        contribution_point=point,
                        identifier=identifier,
                        project_id=project_id,
                    )
                )
                registered.append(_contribution_data(contribution))
            uow.commit()
        return {"registered": registered, "skipped": skipped}

    def list_contributions(
        self,
        project_id: ProjectId,
        *,
        plugin_id: str | None = None,
        contribution_point: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            repository = PluginRepository(RepositoryContext(session=session, project_id=project_id))
            records = repository.list_contributions(
                project_id=project_id,
                plugin_id=plugin_id,
                contribution_point=contribution_point,
            )
            global_enabled = repository.get_global_enabled()
            output = []
            for record in records:
                registration = repository.get_registration(record.plugin_id)
                grant = repository.get_active_grant(record.plugin_id, record.required_capability, project_id)
                output.append(
                    {
                        **_contribution_data(record),
                        "live_enabled": bool(global_enabled and registration and registration.is_enabled and record.is_enabled and grant),
                    }
                )
            return output

    def invoke_contribution(self, contribution_id: str, project_id: ProjectId, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            repository = PluginRepository(RepositoryContext(session=session, project_id=project_id))
            contribution = repository.get_contribution(contribution_id)
            if contribution is None or contribution.project_id != str(project_id):
                raise PluginApplicationError(ErrorCode.NOT_FOUND, f"Contribution not found: {contribution_id}")
            registration = repository.get_registration(contribution.plugin_id)
            grant = repository.get_active_grant(contribution.plugin_id, contribution.required_capability, project_id)
            if not repository.get_global_enabled() or registration is None or not registration.is_enabled or not contribution.is_enabled or grant is None:
                raise PluginApplicationError(ErrorCode.PRECONDITION_FAILED, "Contribution is disabled by plugin state, kill switch, or capability grant")
            point = contribution.contribution_point
            identifier = contribution.identifier
            plugin_id = contribution.plugin_id
            plugin_key = registration.plugin_key
        mode = f"contribution:{point}:{identifier}"
        result = self._container.create_plugin_host_service().run_plugin(plugin_id, project_id, mode=mode)
        contribution_results = result.get("contribution_results", [])
        contribution_result = contribution_results[-1].get("result", {}) if contribution_results else {}
        event_factory = plugin_contribution_invoked
        reason = None
        if result.get("status") in {"failed", "crashed", "timed_out"}:
            event_factory = plugin_contribution_failed
            reason = str(result.get("failure_summary") or result.get("status"))
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            if reason:
                uow.collect_event(
                    plugin_contribution_failed(
                        plugin_key,
                        contribution_id=contribution_id,
                        contribution_point=point,
                        project_id=project_id,
                        reason=reason,
                    )
                )
            else:
                uow.collect_event(
                    plugin_contribution_invoked(
                        plugin_key,
                        contribution_id=contribution_id,
                        contribution_point=point,
                        project_id=project_id,
                    )
                )
            uow.commit()
        return {
            "contribution_id": contribution_id,
            "contribution_point": point,
            "identifier": identifier,
            "runtime": result,
            "result": contribution_result,
        }

    def _missing_project(self, project_id: ProjectId) -> None:
        raise PluginApplicationError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")


def _manifest_contributions(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw = manifest.get("contributions") or []
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _contribution_data(record: Any) -> dict[str, Any]:
    return {
        "contribution_id": record.contribution_id,
        "plugin_id": record.plugin_id,
        "project_id": record.project_id,
        "contribution_point": record.contribution_point,
        "identifier": record.identifier,
        "required_capability": record.required_capability,
        "descriptor": record.descriptor_json,
        "is_enabled": bool(record.is_enabled),
        "registered_at": record.registered_at,
        "disabled_at": record.disabled_at,
    }
