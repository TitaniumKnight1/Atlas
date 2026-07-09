from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from backend.adapters.persistence.models import AuditEventRecord, CommandExecutionRecord, CommandPlanRecord, DomainEventRecord, ProjectRecord
from backend.domain.shared_kernel import AggregateRef, DomainEventEnvelope, ProjectId
from backend.infrastructure.di import create_application_container


def test_preview_and_dry_run_do_not_persist(tmp_path: Path) -> None:
    root = _project_root(tmp_path, "preview-project")
    container = create_application_container(tmp_path / "app-data")
    try:
        service = container.create_project_service()
        preview = service.preview_import_project(root)
        dry_run = service.dry_run_import_project(root)

        assert preview.preview["root_path"] == str(root.resolve())
        assert dry_run.valid is True
        assert _count(container, ProjectRecord) == 0
        assert _count(container, CommandPlanRecord) == 0
        assert _count(container, AuditEventRecord) == 0
    finally:
        container.close()


def test_execute_persists_survives_restart_and_publishes_event(tmp_path: Path) -> None:
    root = _project_root(tmp_path, "persistent-project")
    app_data = tmp_path / "app-data"
    container = create_application_container(app_data)
    seen: list[str] = []
    container.event_bus.register("ProjectImported", lambda event: seen.append(str(event.project_id)))
    try:
        result = container.create_project_service().execute_import_project(root_path=root)
        project_id = result.result["project_id"]

        assert seen == [project_id]
        assert _count(container, ProjectRecord) == 1
        assert _count(container, CommandPlanRecord) == 1
        assert _count(container, CommandExecutionRecord) == 1
        assert _count(container, AuditEventRecord) == 1
        assert _count(container, DomainEventRecord) == 1
    finally:
        container.close()

    restarted = create_application_container(app_data)
    try:
        projects = restarted.create_project_service().list_projects()
        assert [project["project_id"] for project in projects] == [project_id]
    finally:
        restarted.close()


def test_undo_uses_compensation_and_is_audited(tmp_path: Path) -> None:
    root = _project_root(tmp_path, "undo-project")
    container = create_application_container(tmp_path / "app-data")
    seen: list[str] = []
    container.event_bus.register("ProjectArchived", lambda event: seen.append(event.event_type))
    try:
        service = container.create_project_service()
        result = service.execute_import_project(root_path=root)
        assert result.undo_plan is not None

        undo_result = service.undo(result.undo_plan)
        project = service.get_project(ProjectId(result.result["project_id"]))

        assert undo_result.command_type == "UndoImportProject"
        assert project["status"] == "archived"
        assert seen == ["ProjectArchived"]
        assert _count(container, CommandExecutionRecord) == 2
        assert _count(container, AuditEventRecord) == 2
    finally:
        container.close()


def test_project_id_scoping_isolates_settings(tmp_path: Path) -> None:
    first_root = _project_root(tmp_path, "first-project")
    second_root = _project_root(tmp_path, "second-project")
    container = create_application_container(tmp_path / "app-data")
    try:
        service = container.create_project_service()
        first = ProjectId(service.execute_import_project(root_path=first_root).result["project_id"])
        second = ProjectId(service.execute_import_project(root_path=second_root).result["project_id"])

        service.update_project_settings(project_id=first, patch={"server.name": "First"})

        assert service.get_project_settings(first) == {"server.name": "First"}
        assert service.get_project_settings(second) == {}
    finally:
        container.close()


def test_reimport_same_path_replaces_metadata(tmp_path: Path) -> None:
    root = _project_root(tmp_path, "prevailrp")
    container = create_application_container(tmp_path / "app-data")
    try:
        service = container.create_project_service()
        first = service.execute_import_project(root_path=root)
        first_id = first.result["project_id"]
        service.update_project_settings(project_id=ProjectId(first_id), patch={"server.name": "Prevail"})
        service.archive_project(ProjectId(first_id), "Fixture reset")

        second = service.execute_import_project(root_path=root)
        assert second.result["project_id"] == first_id
        assert second.result["replaced_existing_project"] is True
        project = service.get_project(ProjectId(first_id))
        assert project["status"] == "active"
        assert service.get_project_settings(ProjectId(first_id)) == {}
        assert _count(container, ProjectRecord) == 1
    finally:
        container.close()


def test_reimport_same_slug_different_path_conflicts(tmp_path: Path) -> None:
    first_root = _project_root(tmp_path, "prevailrp")
    second_root = _project_root(tmp_path / "other", "prevailrp")
    container = create_application_container(tmp_path / "app-data")
    try:
        service = container.create_project_service()
        service.execute_import_project(root_path=first_root)
        try:
            service.execute_import_project(root_path=second_root)
            raise AssertionError("expected conflict")
        except Exception as error:
            assert "different folder" in str(error)
    finally:
        container.close()


def test_rollback_does_not_publish_collected_events(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    seen: list[str] = []
    container.event_bus.register("RolledBackProjectEvent", lambda event: seen.append(event.event_type))
    try:
        with container.create_unit_of_work(ProjectId("project-rollback")) as uow:
            uow.begin()
            uow.collect_event(
                DomainEventEnvelope.create(
                    event_type="RolledBackProjectEvent",
                    aggregate_ref=AggregateRef("Project", "project-rollback"),
                    project_id=ProjectId("project-rollback"),
                )
            )
            uow.rollback()

        assert seen == []
    finally:
        container.close()


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / "resources").mkdir(parents=True)
    return root


def _count(container, model: type) -> int:
    with container.session_factory() as session:
        return len(list(session.execute(select(model)).scalars()))
