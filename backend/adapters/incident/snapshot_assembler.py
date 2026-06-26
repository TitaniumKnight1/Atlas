from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from backend.adapters.git import redact_remote_url
from backend.adapters.persistence.models import DomainEventRecord, SetupProcessRunRecord
from backend.domain.incident import BOUNDED_LOG_TAIL_LIMIT, ContextSnapshotType, RedactionState
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.unit_of_work import RepositoryContext


@dataclass(frozen=True, slots=True)
class AssembledSnapshot:
    message: str
    context_snapshots: list[dict[str, Any]]
    breadcrumbs: list[dict[str, Any]]
    stack_trace: dict[str, Any] | None


class IncidentSnapshotAssembler:
    """Reads M3b/M4/M5/M6 capabilities — does not re-implement them."""

    def __init__(self, container: Any) -> None:
        self._container = container

    def assemble(self, project_id: ProjectId, *, process_run_id: str, exit_code: int | None) -> AssembledSnapshot:
        now = datetime.now(UTC)
        process = self._read_process(project_id, process_run_id)
        resources = self._read_resources(project_id)
        startup_order = self._read_startup_order(project_id)
        config_state = self._read_config_state(project_id)
        git_state = self._read_git_state(project_id)
        metrics = self._read_metrics(project_id)
        logs = self._read_logs(process)
        breadcrumbs = self._read_breadcrumbs(project_id, process_run_id, now)
        message = f"Server process exited unexpectedly with code {exit_code}" if exit_code is not None else "Server process exited unexpectedly"
        snapshots = [
            self._snapshot(ContextSnapshotType.RUNTIME, process, RedactionState.RAW_LOCAL, now),
            self._snapshot(ContextSnapshotType.RESOURCES, resources, RedactionState.RAW_LOCAL, now),
            self._snapshot(ContextSnapshotType.STARTUP_ORDER, startup_order, RedactionState.RAW_LOCAL, now),
            self._snapshot(ContextSnapshotType.CONFIG_EXCERPT, config_state, RedactionState.REDACTED, now),
            self._snapshot(ContextSnapshotType.ENVIRONMENT, git_state, RedactionState.REDACTED, now),
            self._snapshot(ContextSnapshotType.SYSTEM, metrics, RedactionState.RAW_LOCAL, now),
            self._snapshot(ContextSnapshotType.LOGS, logs, RedactionState.RAW_LOCAL, now),
        ]
        stack_trace = {
            "exception_type": None,
            "exception_value": message,
            "language": "unknown",
            "available": False,
            "note": "No structured stack trace provided by M3b crash detection; exit code only.",
        }
        return AssembledSnapshot(message=message, context_snapshots=snapshots, breadcrumbs=breadcrumbs, stack_trace=stack_trace)

    def _read_process(self, project_id: ProjectId, process_run_id: str) -> dict[str, Any]:
        setup = self._container.create_setup_service()
        try:
            status = setup.get_process_status(project_id, process_run_id)
        except Exception:
            with self._container.session_factory() as session:
                record = session.get(SetupProcessRunRecord, process_run_id)
                if record is None:
                    return {"available": False, "reason": "process_run_not_found"}
                return {
                    "available": True,
                    "process_run_id": record.process_run_id,
                    "state": record.state,
                    "pid": record.pid,
                    "exit_code": record.exit_code,
                    "started_at": record.started_at,
                    "stopped_at": record.stopped_at,
                }
        return {"available": True, **status}

    def _read_resources(self, project_id: ProjectId) -> dict[str, Any]:
        service = self._container.create_resource_service()
        resources = service.list_resources(project_id)
        graph = service.get_dependency_graph(project_id)
        return {"resources": resources, "dependency_graph": graph}

    def _read_startup_order(self, project_id: ProjectId) -> dict[str, Any]:
        return self._container.create_resource_service().get_safe_start_order(project_id)

    def _read_config_state(self, project_id: ProjectId) -> dict[str, Any]:
        config = self._container.create_config_service()
        files = config.list_config_files(project_id)
        findings = config.list_secret_findings(project_id, status="open")
        return {
            "config_files": [
                {
                    "config_file_id": item["config_file_id"],
                    "path": item["path"],
                    "file_role": item.get("file_role"),
                    "validation_status": item.get("validation_status"),
                }
                for item in files
            ],
            "secret_findings": [
                {
                    "secret_finding_id": item["secret_finding_id"],
                    "config_file_id": item["config_file_id"],
                    "path": item["path"],
                    "severity": item["severity"],
                    "secret_type": item.get("secret_type"),
                    "status": item["status"],
                    "note": "Secret values are not included in incident snapshots.",
                }
                for item in findings
            ],
        }

    def _read_git_state(self, project_id: ProjectId) -> dict[str, Any]:
        git = self._container.create_git_service()
        repos = git.list_git_repositories(project_id)
        snapshots: list[dict[str, Any]] = []
        for repo in repos:
            status = git.get_worktree_status(project_id, repo["git_repository_id"])
            snapshots.append(
                {
                    "git_repository_id": repo["git_repository_id"],
                    "repository_role": repo.get("repository_role"),
                    "local_path": repo.get("local_path"),
                    "remote_url": redact_remote_url(repo.get("remote_url")),
                    "current_branch": status.get("branch_name"),
                    "head_commit_sha": status.get("head_commit_sha"),
                    "is_dirty": status.get("is_dirty"),
                }
            )
        return {"repositories": snapshots}

    def _read_metrics(self, project_id: ProjectId) -> dict[str, Any]:
        monitoring = self._container.create_monitoring_service()
        retention = self._container.create_monitoring_retention_service()
        now = datetime.now(UTC)
        window_start = now - timedelta(hours=1)
        latest = monitoring.latest_metrics(project_id)
        history = retention.query_time_window(project_id, start_at=window_start, end_at=now, resolution="minute")
        return {"latest_samples": latest, "recent_minute_rollups": history}

    def _read_logs(self, process: dict[str, Any]) -> dict[str, Any]:
        stdout = process.get("stdout_tail") or []
        stderr = process.get("stderr_tail") or []
        return {
            "availability": "bounded_tail_only",
            "durable_history_available": False,
            "max_lines_per_stream": BOUNDED_LOG_TAIL_LIMIT,
            "stdout_line_count": len(stdout),
            "stderr_line_count": len(stderr),
            "stdout_tail": stdout,
            "stderr_tail": stderr,
            "note": (
                "M3b persists only bounded in-memory tails (max 200 lines per stream), not durable log history. "
                "Snapshot includes whatever was buffered at crash time."
            ),
        }

    def _read_breadcrumbs(self, project_id: ProjectId, process_run_id: str, now: datetime) -> list[dict[str, Any]]:
        crumbs: list[dict[str, Any]] = [
            {
                "timestamp": now.isoformat(),
                "category": "process",
                "level": "fatal",
                "message": f"Server process crash detected for run {process_run_id}",
                "data": {"process_run_id": process_run_id},
            }
        ]
        with self._container.session_factory() as session:
            rows = session.execute(
                select(DomainEventRecord)
                .where(DomainEventRecord.project_id == str(project_id))
                .order_by(DomainEventRecord.occurred_at.desc())
                .limit(10)
            ).scalars()
            for index, row in enumerate(reversed(list(rows))):
                crumbs.append(
                    {
                        "timestamp": row.occurred_at,
                        "category": "server",
                        "level": "info",
                        "message": row.event_type,
                        "data": row.payload_json or {},
                        "sort_order": index + 1,
                    }
                )
        for index, item in enumerate(crumbs):
            item.setdefault("sort_order", index)
        return crumbs

    def _snapshot(self, context_type: ContextSnapshotType, payload: dict[str, Any], redaction_state: RedactionState, captured_at: datetime) -> dict[str, Any]:
        return {
            "context_type": context_type.value,
            "snapshot_json": payload,
            "redaction_state": redaction_state.value,
            "captured_at": captured_at.isoformat(),
        }
