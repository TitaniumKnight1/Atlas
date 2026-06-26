from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.domain.shared_kernel.identifiers import ProjectId
from backend.infrastructure.event_bus import InProcessEventBus
from backend.infrastructure.unit_of_work import SingleWriterSQLiteUnitOfWork, create_session_factory, create_sqlite_engine


@dataclass(slots=True)
class ApplicationContainer:
    app_data_dir: Path
    engine: Engine
    session_factory: sessionmaker[Session]
    event_bus: InProcessEventBus
    writer_lock: RLock = field(default_factory=RLock)

    def create_unit_of_work(self, project_id: ProjectId | None = None) -> SingleWriterSQLiteUnitOfWork:
        return SingleWriterSQLiteUnitOfWork(
            session_factory=self.session_factory,
            event_bus=self.event_bus,
            writer_lock=self.writer_lock,
            project_id=project_id,
        )

    def close(self) -> None:
        self.engine.dispose()


def create_application_container(app_data_dir: Path) -> ApplicationContainer:
    engine = create_sqlite_engine(app_data_dir)
    return ApplicationContainer(
        app_data_dir=app_data_dir,
        engine=engine,
        session_factory=create_session_factory(engine),
        event_bus=InProcessEventBus(),
    )
