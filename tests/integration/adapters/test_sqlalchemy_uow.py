from __future__ import annotations

import threading
import time
from pathlib import Path

from sqlalchemy import Column, MetaData, String, Table, insert, select

from backend.domain.shared_kernel import AggregateRef, DomainEventEnvelope, ProjectId
from backend.infrastructure.di import ApplicationContainer, create_application_container
from backend.infrastructure.unit_of_work import RepositoryContext


METADATA = MetaData()
RECORDS = Table(
    "m0b_uow_records",
    METADATA,
    Column("record_id", String, primary_key=True),
    Column("project_id", String, nullable=False),
    Column("record_value", String, nullable=False),
)


class RecordRepository:
    def __init__(self, context: RepositoryContext) -> None:
        self._context = context

    def add(self, record_id: str, value: str) -> None:
        project_id = self._context.require_project_id()
        self._context.session.execute(
            insert(RECORDS).values(record_id=record_id, project_id=str(project_id), record_value=value)
        )


def test_uow_commits_and_rolls_back_sqlalchemy_writes(tmp_path: Path) -> None:
    container = _container(tmp_path)
    project_id = ProjectId("project-commit")
    try:
        with container.create_unit_of_work(project_id) as unit_of_work:
            unit_of_work.begin()
            unit_of_work.repository(RecordRepository).add("commit-1", "committed")
            unit_of_work.commit()

        with container.create_unit_of_work(project_id) as unit_of_work:
            unit_of_work.begin()
            unit_of_work.repository(RecordRepository).add("rollback-1", "rolled-back")
            unit_of_work.rollback()

        assert _record_values(container) == ["committed"]
    finally:
        container.close()


def test_domain_events_publish_after_commit_but_not_after_rollback(tmp_path: Path) -> None:
    container = _container(tmp_path)
    project_id = ProjectId("project-events")
    seen: list[str] = []
    container.event_bus.register("InfrastructureCommitted", lambda event: seen.append(str(event.event_id)))
    try:
        committed = DomainEventEnvelope.create(
            event_type="InfrastructureCommitted",
            aggregate_ref=AggregateRef("Infrastructure", "commit"),
            project_id=project_id,
        )
        rolled_back = DomainEventEnvelope.create(
            event_type="InfrastructureCommitted",
            aggregate_ref=AggregateRef("Infrastructure", "rollback"),
            project_id=project_id,
        )

        with container.create_unit_of_work(project_id) as unit_of_work:
            unit_of_work.begin()
            unit_of_work.collect_event(committed)
            unit_of_work.commit()

        with container.create_unit_of_work(project_id) as unit_of_work:
            unit_of_work.begin()
            unit_of_work.collect_event(rolled_back)
            unit_of_work.rollback()

        assert seen == [str(committed.event_id)]
    finally:
        container.close()


def test_single_writer_lock_serializes_commit_and_post_commit_dispatch(tmp_path: Path) -> None:
    container = _container(tmp_path)
    project_id = ProjectId("project-lock")
    handler_started = threading.Event()
    handler_finished = threading.Event()
    timings: dict[str, float] = {}
    errors: list[BaseException] = []

    def slow_handler(_event: DomainEventEnvelope) -> None:
        timings["handler_start"] = time.perf_counter()
        handler_started.set()
        time.sleep(0.15)
        timings["handler_end"] = time.perf_counter()
        handler_finished.set()

    container.event_bus.register("InfrastructureCommitted", slow_handler)

    def first_writer() -> None:
        try:
            event = DomainEventEnvelope.create(
                event_type="InfrastructureCommitted",
                aggregate_ref=AggregateRef("Infrastructure", "first"),
                project_id=project_id,
            )
            with container.create_unit_of_work(project_id) as unit_of_work:
                unit_of_work.begin()
                unit_of_work.repository(RecordRepository).add("first", "first")
                unit_of_work.collect_event(event)
                unit_of_work.commit()
        except BaseException as error:  # noqa: BLE001 - surfaced after thread joins.
            errors.append(error)

    def second_writer() -> None:
        try:
            assert handler_started.wait(timeout=2)
            timings["second_attempt"] = time.perf_counter()
            with container.create_unit_of_work(project_id) as unit_of_work:
                unit_of_work.begin()
                timings["second_begin"] = time.perf_counter()
                unit_of_work.repository(RecordRepository).add("second", "second")
                unit_of_work.commit()
        except BaseException as error:  # noqa: BLE001 - surfaced after thread joins.
            errors.append(error)

    try:
        first = threading.Thread(target=first_writer)
        second = threading.Thread(target=second_writer)
        first.start()
        second.start()
        first.join(timeout=5)
        second.join(timeout=5)

        assert not first.is_alive()
        assert not second.is_alive()
        assert errors == []
        assert handler_finished.is_set()
        assert timings["second_attempt"] < timings["handler_end"]
        assert timings["second_begin"] >= timings["handler_end"]
        assert _record_values(container) == ["first", "second"]
    finally:
        container.close()


def _container(tmp_path: Path) -> ApplicationContainer:
    container = create_application_container(tmp_path)
    METADATA.create_all(container.engine)
    return container


def _record_values(container: ApplicationContainer) -> list[str]:
    with container.session_factory() as session:
        return list(session.execute(select(RECORDS.c.record_value).order_by(RECORDS.c.record_id)).scalars())
