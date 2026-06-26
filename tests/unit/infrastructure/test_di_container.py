from __future__ import annotations

from types import SimpleNamespace

from backend.api.dependencies import get_container, get_unit_of_work
from backend.infrastructure.di import ApplicationContainer, create_application_container
from backend.infrastructure.unit_of_work import SingleWriterSQLiteUnitOfWork


def test_container_resolves_uow_and_event_bus_without_global_singleton(tmp_path) -> None:
    first = create_application_container(tmp_path / "first")
    second = create_application_container(tmp_path / "second")
    try:
        assert isinstance(first, ApplicationContainer)
        assert isinstance(first.create_unit_of_work(), SingleWriterSQLiteUnitOfWork)
        assert first.event_bus is not second.event_bus
        assert first.writer_lock is not second.writer_lock
    finally:
        first.close()
        second.close()


def test_fastapi_dependencies_resolve_from_request_app_state(tmp_path) -> None:
    container = create_application_container(tmp_path)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(container=container)))
    try:
        assert get_container(request) is container

        dependency = get_unit_of_work(container)
        unit_of_work = next(dependency)
        assert isinstance(unit_of_work, SingleWriterSQLiteUnitOfWork)
        try:
            next(dependency)
        except StopIteration:
            pass
        else:
            raise AssertionError("Unit of Work dependency did not finish")
    finally:
        container.close()
