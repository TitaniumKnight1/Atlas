from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.adapters.filesystem import LocalProjectFilesystemInspector, LocalSetupFilesystem
from backend.adapters.fivem import CfxArtifactClient
from backend.adapters.persistence.schema import bootstrap_schema
from backend.adapters.process import LocalProcessSupervisor
from backend.adapters.streams import StreamEventBridge, StreamEventPublisher
from backend.adapters.telemetry import DeterministicTelemetrySanitizer, LocalNoopTelemetryDelivery
from backend.adapters.txadmin import LocalTxAdminDetector
from backend.application.project.service import ProjectApplicationService
from backend.adapters.config import FiveMConfigValidator, LocalConfigSecretScanner
from backend.application.config.service import ConfigApplicationService
from backend.application.setup.service import SetupApplicationService
from backend.application.telemetry.service import TelemetryApplicationService
from backend.domain.shared_kernel.identifiers import ProjectId
from backend.infrastructure.event_bus import InProcessEventBus
from backend.infrastructure.streams import ProjectStreamHub
from backend.infrastructure.unit_of_work import SingleWriterSQLiteUnitOfWork, create_session_factory, create_sqlite_engine


@dataclass(slots=True)
class ApplicationContainer:
    app_data_dir: Path
    engine: Engine
    session_factory: sessionmaker[Session]
    event_bus: InProcessEventBus
    stream_hub: ProjectStreamHub
    stream_publisher: StreamEventPublisher
    stream_bridge: StreamEventBridge
    filesystem_inspector: LocalProjectFilesystemInspector
    setup_filesystem: LocalSetupFilesystem
    artifact_client: CfxArtifactClient
    process_supervisor: LocalProcessSupervisor
    txadmin_detector: LocalTxAdminDetector
    telemetry_sanitizer: DeterministicTelemetrySanitizer
    telemetry_delivery: LocalNoopTelemetryDelivery
    writer_lock: RLock = field(default_factory=RLock)

    def create_unit_of_work(self, project_id: ProjectId | None = None) -> SingleWriterSQLiteUnitOfWork:
        return SingleWriterSQLiteUnitOfWork(
            session_factory=self.session_factory,
            event_bus=self.event_bus,
            writer_lock=self.writer_lock,
            project_id=project_id,
        )

    def create_project_service(self) -> ProjectApplicationService:
        return ProjectApplicationService(container=self, filesystem_inspector=self.filesystem_inspector)

    def create_telemetry_service(self) -> TelemetryApplicationService:
        return TelemetryApplicationService(
            container=self,
            sanitizer=self.telemetry_sanitizer,
            delivery=self.telemetry_delivery,
        )

    def create_config_service(self) -> ConfigApplicationService:
        return ConfigApplicationService(
            container=self,
            filesystem=self.setup_filesystem,
            validator=FiveMConfigValidator(),
            secret_scanner=LocalConfigSecretScanner(),
        )

    def create_setup_service(self) -> SetupApplicationService:
        service = SetupApplicationService(
            container=self,
            artifact_client=self.artifact_client,
            filesystem=self.setup_filesystem,
            process_port=self.process_supervisor,
            txadmin=self.txadmin_detector,
            stream_publisher=self.stream_publisher,
        )
        self.process_supervisor.set_on_exit(service.record_process_exit)
        self.process_supervisor.set_on_line(self._publish_server_output_line)
        return service

    def _publish_server_output_line(self, process_run_id: str, project_id: str, stream: str, line: str) -> None:
        self.stream_publisher.publish_server_output_line(
            project_id=ProjectId(project_id),
            process_run_id=process_run_id,
            stream=stream,
            line=line,
        )

    def close(self) -> None:
        self.engine.dispose()


def create_application_container(app_data_dir: Path) -> ApplicationContainer:
    engine = create_sqlite_engine(app_data_dir)
    bootstrap_schema(engine)
    event_bus = InProcessEventBus()
    stream_hub = ProjectStreamHub()
    stream_publisher = StreamEventPublisher(event_bus)
    stream_bridge = StreamEventBridge(stream_hub)
    stream_bridge.register(event_bus)
    return ApplicationContainer(
        app_data_dir=app_data_dir,
        engine=engine,
        session_factory=create_session_factory(engine),
        event_bus=event_bus,
        stream_hub=stream_hub,
        stream_publisher=stream_publisher,
        stream_bridge=stream_bridge,
        filesystem_inspector=LocalProjectFilesystemInspector(),
        setup_filesystem=LocalSetupFilesystem(),
        artifact_client=CfxArtifactClient(),
        process_supervisor=LocalProcessSupervisor(),
        txadmin_detector=LocalTxAdminDetector(),
        telemetry_sanitizer=DeterministicTelemetrySanitizer(),
        telemetry_delivery=LocalNoopTelemetryDelivery(),
    )
