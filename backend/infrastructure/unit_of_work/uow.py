from __future__ import annotations

from threading import RLock
from types import TracebackType

from sqlalchemy.orm import Session, SessionTransaction, sessionmaker

from backend.domain.shared_kernel.events import DomainEventEnvelope
from backend.domain.shared_kernel.identifiers import ProjectId
from backend.infrastructure.event_bus import InProcessEventBus
from backend.infrastructure.unit_of_work.repository import RepositoryContext, TRepository, TypedRepositoryFactory


class UnitOfWorkStateError(RuntimeError):
    """Raised when a Unit of Work operation violates its lifecycle."""


class SingleWriterSQLiteUnitOfWork:
    """Explicit SQLAlchemy Unit of Work for Atlas SQLite writes.

    The writer lock is held from `begin()` through commit/rollback cleanup so
    every write transaction enters SQLite through one serialized path.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        event_bus: InProcessEventBus,
        writer_lock: RLock,
        project_id: ProjectId | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._event_bus = event_bus
        self._writer_lock = writer_lock
        self._project_id = project_id
        self._session: Session | None = None
        self._transaction: SessionTransaction | None = None
        self._events: list[DomainEventEnvelope] = []
        self._active = False
        self._finished = False

    @property
    def project_id(self) -> ProjectId | None:
        return self._project_id

    @property
    def session(self) -> Session:
        if self._session is None or not self._active:
            raise UnitOfWorkStateError("Unit of Work is not active; call begin() first")
        return self._session

    def __enter__(self) -> SingleWriterSQLiteUnitOfWork:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        if self._active:
            self.rollback()

    def begin(self) -> SingleWriterSQLiteUnitOfWork:
        if self._active or self._finished:
            raise UnitOfWorkStateError("Unit of Work cannot be begun more than once")

        self._writer_lock.acquire()
        try:
            self._session = self._session_factory()
            self._transaction = self._session.begin()
            self._active = True
            return self
        except Exception:
            self._release_writer()
            raise

    def repository(self, factory: TypedRepositoryFactory[TRepository]) -> TRepository:
        return factory(RepositoryContext(session=self.session, project_id=self._project_id))

    def collect_event(self, event: DomainEventEnvelope) -> None:
        if not self._active:
            raise UnitOfWorkStateError("Domain events can only be collected inside an active Unit of Work")
        if event.project_id is None and self._project_id is not None:
            raise UnitOfWorkStateError("Project-scoped Unit of Work cannot collect an unscoped event")
        if event.project_id is not None and self._project_id is not None and event.project_id != self._project_id:
            raise UnitOfWorkStateError("Domain event project_id does not match Unit of Work project_id")
        self._events.append(event)

    def commit(self) -> None:
        self._require_active()
        events = tuple(self._events)
        try:
            assert self._transaction is not None
            self._transaction.commit()
        except Exception:
            self._rollback_open_transaction()
            self._events.clear()
            raise
        else:
            self._active = False
            self._finished = True
            try:
                self._event_bus.publish(events)
            finally:
                self._close_session()
                self._release_writer()

    def rollback(self) -> None:
        if not self._active:
            return
        try:
            self._rollback_open_transaction()
            self._events.clear()
        finally:
            self._active = False
            self._finished = True
            self._close_session()
            self._release_writer()

    def _require_active(self) -> None:
        if not self._active:
            raise UnitOfWorkStateError("Unit of Work is not active")

    def _rollback_open_transaction(self) -> None:
        if self._transaction is not None and self._transaction.is_active:
            self._transaction.rollback()

    def _close_session(self) -> None:
        if self._session is not None:
            self._session.close()
        self._session = None
        self._transaction = None

    def _release_writer(self) -> None:
        self._writer_lock.release()
