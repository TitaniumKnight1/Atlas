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
from backend.adapters.telemetry import DeterministicTelemetrySanitizer, LocalNoopTelemetryDelivery, create_telemetry_delivery
from backend.adapters.txadmin import LocalTxAdminDetector
from backend.application.automation.service import AutomationApplicationService
from backend.application.backup import BackupApplicationService, BackupSchedulerService
from backend.application.incident.service import IncidentApplicationService
from backend.application.monitoring.alerts import MonitoringAlertService
from backend.application.monitoring.retention import MonitoringRetentionService
from backend.application.monitoring.service import MonitoringApplicationService
from backend.application.plugin.service import PluginApplicationService
from backend.application.project.service import ProjectApplicationService
from backend.adapters.config import FiveMConfigValidator, LocalConfigSecretScanner
from backend.adapters.git import GitPythonProvider
from backend.application.config.service import ConfigApplicationService
from backend.application.git.service import GitApplicationService
from backend.application.resources.service import ResourceApplicationService
from backend.application.setup.service import SetupApplicationService
from backend.application.telemetry.service import TelemetryApplicationService
from backend.domain.telemetry import TelemetryDeliveryPort
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
    telemetry_delivery: TelemetryDeliveryPort
    writer_lock: RLock = field(default_factory=RLock)
    _monitoring_service: MonitoringApplicationService | None = field(default=None, repr=False)
    _monitoring_retention_service: MonitoringRetentionService | None = field(default=None, repr=False)
    _monitoring_alert_service: MonitoringAlertService | None = field(default=None, repr=False)
    _incident_service: IncidentApplicationService | None = field(default=None, repr=False)
    _automation_service: AutomationApplicationService | None = field(default=None, repr=False)
    _backup_service: BackupApplicationService | None = field(default=None, repr=False)
    _backup_scheduler_service: BackupSchedulerService | None = field(default=None, repr=False)
    _plugin_service: PluginApplicationService | None = field(default=None, repr=False)

    def create_unit_of_work(self, project_id: ProjectId | None = None) -> SingleWriterSQLiteUnitOfWork:
        return SingleWriterSQLiteUnitOfWork(
            session_factory=self.session_factory,
            event_bus=self.event_bus,
            writer_lock=self.writer_lock,
            project_id=project_id,
        )

    def create_plugin_host_service(self) -> PluginHostService:
        from backend.application.plugin.host_service import PluginHostService

        return PluginHostService(container=self)

    def create_plugin_contribution_service(self):
        from backend.application.plugin.contributions import PluginContributionService

        return PluginContributionService(container=self)

    def create_plugin_service(self) -> PluginApplicationService:
        if self._plugin_service is None:
            self._plugin_service = PluginApplicationService(container=self)
        return self._plugin_service

    def create_project_service(self) -> ProjectApplicationService:
        return ProjectApplicationService(container=self, filesystem_inspector=self.filesystem_inspector)

    def create_telemetry_service(self) -> TelemetryApplicationService:
        return TelemetryApplicationService(
            container=self,
            sanitizer=self.telemetry_sanitizer,
            delivery=self.telemetry_delivery,
        )

    def create_git_service(self) -> GitApplicationService:
        return GitApplicationService(
            container=self,
            provider=GitPythonProvider(),
            stream_publisher=self.stream_publisher,
        )

    def create_config_service(self) -> ConfigApplicationService:
        return ConfigApplicationService(
            container=self,
            filesystem=self.setup_filesystem,
            validator=FiveMConfigValidator(),
            secret_scanner=LocalConfigSecretScanner(),
        )

    def create_resource_service(self) -> ResourceApplicationService:
        return ResourceApplicationService(container=self, filesystem=self.setup_filesystem)

    def create_resource_lifecycle_service(self) -> ResourceLifecycleService:
        from backend.application.resources.lifecycle import ResourceLifecycleService

        return ResourceLifecycleService(
            container=self,
            filesystem=self.setup_filesystem,
            stream_publisher=self.stream_publisher,
        )

    def create_resource_rollback_service(self) -> ResourceRollbackService:
        from backend.application.resources.rollback import ResourceRollbackService

        return ResourceRollbackService(
            container=self,
            filesystem=self.setup_filesystem,
            stream_publisher=self.stream_publisher,
        )

    def create_automation_service(self) -> AutomationApplicationService:
        if self._automation_service is None:
            self._automation_service = AutomationApplicationService(container=self)
            self._automation_service.register_event_subscribers()
            self._automation_service.start_scheduler()
        return self._automation_service

    def create_backup_service(self) -> BackupApplicationService:
        if self._backup_service is None:
            self._backup_service = BackupApplicationService(container=self)
        return self._backup_service

    def create_backup_scheduler_service(self) -> BackupSchedulerService:
        if self._backup_scheduler_service is None:
            self._backup_scheduler_service = BackupSchedulerService(
                container=self,
                backup_service=self.create_backup_service(),
            )
            self._backup_scheduler_service.start()
        return self._backup_scheduler_service

    def create_incident_service(self) -> IncidentApplicationService:
        if self._incident_service is None:
            self._incident_service = IncidentApplicationService(container=self)
            self._incident_service.register_crash_subscriber()
        return self._incident_service

    def create_monitoring_alert_service(self) -> MonitoringAlertService:
        if self._monitoring_alert_service is None:
            self._monitoring_alert_service = MonitoringAlertService(
                container=self,
                stream_publisher=self.stream_publisher,
            )
        return self._monitoring_alert_service

    def create_monitoring_retention_service(self) -> MonitoringRetentionService:
        if self._monitoring_retention_service is None:
            self._monitoring_retention_service = MonitoringRetentionService(container=self)
        return self._monitoring_retention_service

    def create_monitoring_service(self) -> MonitoringApplicationService:
        if self._monitoring_service is None:
            self._monitoring_service = MonitoringApplicationService(
                container=self,
                process_port=self.process_supervisor,
                stream_publisher=self.stream_publisher,
            )
        return self._monitoring_service

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
        if self._backup_scheduler_service is not None:
            self._backup_scheduler_service.stop()
        if self._automation_service is not None:
            self._automation_service.stop_scheduler()
        if self._monitoring_alert_service is not None:
            self._monitoring_alert_service.stop_evaluation()
        if self._monitoring_retention_service is not None:
            self._monitoring_retention_service.stop_rollup_scheduler()
        if self._monitoring_service is not None:
            self._monitoring_service.stop_all_collections()
        self.engine.dispose()


def create_application_container(app_data_dir: Path) -> ApplicationContainer:
    engine = create_sqlite_engine(app_data_dir)
    bootstrap_schema(engine)
    event_bus = InProcessEventBus()
    stream_hub = ProjectStreamHub()
    stream_publisher = StreamEventPublisher(event_bus)
    stream_bridge = StreamEventBridge(stream_hub)
    stream_bridge.register(event_bus)
    container = ApplicationContainer(
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
    container.telemetry_delivery = create_telemetry_delivery(container=container, sanitizer=container.telemetry_sanitizer)
    container.create_incident_service()
    container.create_automation_service()
    container.create_backup_scheduler_service()
    return container
