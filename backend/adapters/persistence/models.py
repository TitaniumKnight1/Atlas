from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProjectRecord(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("status in ('active', 'archived', 'missing', 'deleted')", name="ck_projects_status"),
        Index("idx_projects_status_updated_at", "status", "updated_at"),
    )

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, nullable=False)
    default_environment_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    last_opened_at: Mapped[str | None] = mapped_column(String)


class ProjectPathRecord(Base):
    __tablename__ = "project_paths"
    __table_args__ = (
        UniqueConstraint("project_id", "path_role", "absolute_path", name="uq_project_paths_project_role_path"),
        Index("idx_project_paths_project_role", "project_id", "path_role"),
    )

    project_path_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    path_role: Mapped[str] = mapped_column(String, nullable=False)
    absolute_path: Mapped[str] = mapped_column(Text, nullable=False)
    exists_last_checked: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String)
    last_checked_at: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class EnvironmentProfileRecord(Base):
    __tablename__ = "environment_profiles"
    __table_args__ = (
        CheckConstraint("is_default in (0, 1)", name="ck_environment_profiles_is_default"),
        UniqueConstraint("project_id", "name", name="uq_environment_profiles_project_name"),
        Index("idx_environment_profiles_project_default", "project_id", "is_default"),
    )

    environment_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    artifact_channel: Mapped[str | None] = mapped_column(String)
    settings_json: Mapped[dict | None] = mapped_column(JSON)
    is_default: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class ProjectSettingRecord(Base):
    __tablename__ = "project_settings"
    __table_args__ = (
        UniqueConstraint("project_id", "setting_key", name="uq_project_settings_project_key"),
        Index("idx_project_settings_key", "setting_key"),
    )

    project_setting_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    setting_key: Mapped[str] = mapped_column(String, nullable=False)
    value_json: Mapped[object] = mapped_column(JSON, nullable=False)
    value_type: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String)


class WorkspaceTrustDecisionRecord(Base):
    __tablename__ = "workspace_trust_decisions"
    __table_args__ = (
        CheckConstraint("trust_state in ('trusted', 'restricted', 'revoked')", name="ck_workspace_trust_state"),
        UniqueConstraint("project_id", "scope", "scope_ref", name="uq_workspace_trust_scope"),
        Index("idx_workspace_trust_project_state", "project_id", "trust_state"),
    )

    trust_decision_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    trust_state: Mapped[str] = mapped_column(String, nullable=False)
    scope: Mapped[str] = mapped_column(String, nullable=False)
    scope_ref: Mapped[str | None] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[str] = mapped_column(String, nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String)


class ProjectTemplateRecord(Base):
    __tablename__ = "project_templates"
    __table_args__ = (
        CheckConstraint("source_type in ('builtin', 'plugin', 'local')", name="ck_project_templates_source_type"),
        Index("idx_project_templates_source", "source_type", "source_ref"),
    )

    template_id: Mapped[str] = mapped_column(String, primary_key=True)
    template_slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String)
    template_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class AuditEventRecord(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("actor_type in ('user', 'automation', 'plugin', 'system')", name="ck_audit_events_actor_type"),
        Index("idx_audit_events_project_time", "project_id", "occurred_at"),
        Index("idx_audit_events_entity", "entity_type", "entity_id"),
    )

    audit_event_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.project_id"))
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String)
    actor_type: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String)
    occurred_at: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict | None] = mapped_column(JSON)


class CommandPlanRecord(Base):
    __tablename__ = "command_plans"
    __table_args__ = (
        CheckConstraint("status in ('draft', 'presented', 'approved', 'expired', 'cancelled')", name="ck_command_plans_status"),
        CheckConstraint("risk_level in ('low', 'medium', 'high', 'destructive')", name="ck_command_plans_risk"),
        Index("idx_command_plans_project_time", "project_id", "created_at"),
        Index("idx_command_plans_status", "status"),
    )

    command_plan_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.project_id"))
    command_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    risk_level: Mapped[str] = mapped_column(String, nullable=False)
    dry_run_plan_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[str | None] = mapped_column(String)


class CommandExecutionRecord(Base):
    __tablename__ = "command_executions"
    __table_args__ = (
        CheckConstraint("status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')", name="ck_command_executions_status"),
        Index("idx_command_executions_project_time", "project_id", "started_at"),
        Index("idx_command_executions_status", "status"),
    )

    command_execution_id: Mapped[str] = mapped_column(String, primary_key=True)
    command_plan_id: Mapped[str | None] = mapped_column(ForeignKey("command_plans.command_plan_id"))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.project_id"))
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[str | None] = mapped_column(String)
    finished_at: Mapped[str | None] = mapped_column(String)
    idempotency_key: Mapped[str | None] = mapped_column(String, unique=True)
    result_json: Mapped[dict | None] = mapped_column(JSON)
    audit_event_id: Mapped[str | None] = mapped_column(ForeignKey("audit_events.audit_event_id"))


class DomainEventRecord(Base):
    __tablename__ = "domain_events"
    __table_args__ = (
        Index("idx_domain_events_project_time", "project_id", "occurred_at"),
        Index("idx_domain_events_type_time", "event_type", "occurred_at"),
        Index("idx_domain_events_aggregate", "aggregate_type", "aggregate_id"),
    )

    domain_event_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.project_id"))
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String, nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    published_at: Mapped[str | None] = mapped_column(String)


class TelemetryPreferenceRecord(Base):
    __tablename__ = "telemetry_preferences"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_telemetry_preferences_project"),
        CheckConstraint("telemetry_enabled in (0, 1)", name="ck_telemetry_preferences_enabled"),
        CheckConstraint("crash_reporting_enabled in (0, 1)", name="ck_telemetry_preferences_crash"),
        CheckConstraint("plugin_telemetry_enabled in (0, 1)", name="ck_telemetry_preferences_plugin"),
        Index("idx_telemetry_preferences_project", "project_id"),
    )

    telemetry_preference_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.project_id"))
    telemetry_enabled: Mapped[int] = mapped_column(Integer, nullable=False)
    crash_reporting_enabled: Mapped[int] = mapped_column(Integer, nullable=False)
    plugin_telemetry_enabled: Mapped[int] = mapped_column(Integer, nullable=False)
    last_prompted_at: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String)


class TelemetryQueueRecord(Base):
    __tablename__ = "telemetry_queue"
    __table_args__ = (
        CheckConstraint("status in ('queued', 'blocked', 'delivered', 'failed', 'expired')", name="ck_telemetry_queue_status"),
        Index("idx_telemetry_queue_status_next", "status", "next_attempt_at"),
        Index("idx_telemetry_queue_expires", "expires_at"),
    )

    telemetry_event_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    subsystem: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    event_payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    next_attempt_at: Mapped[str | None] = mapped_column(String)
    expires_at: Mapped[str] = mapped_column(String, nullable=False)


class TelemetryRejectionRecord(Base):
    __tablename__ = "telemetry_rejections"
    __table_args__ = (
        CheckConstraint(
            "rejection_reason in ('disabled', 'contains_project_data', 'contains_secret', 'contains_identifier', 'oversized', 'policy')",
            name="ck_telemetry_rejections_reason",
        ),
        Index("idx_telemetry_rejections_reason_time", "rejection_reason", "created_at"),
    )

    telemetry_rejection_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    rejection_reason: Mapped[str] = mapped_column(String, nullable=False)
    subsystem: Mapped[str] = mapped_column(String, nullable=False)
    fingerprint: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    summary_json: Mapped[dict | None] = mapped_column(JSON)


class TelemetrySanitizationResultRecord(Base):
    __tablename__ = "telemetry_sanitization_results"
    __table_args__ = (
        CheckConstraint("result_state in ('allowed', 'redacted', 'rejected')", name="ck_telemetry_sanitization_state"),
        CheckConstraint(
            "telemetry_event_id is not null or telemetry_rejection_id is not null",
            name="ck_telemetry_sanitization_reference",
        ),
        Index("idx_telemetry_sanitization_event", "telemetry_event_id"),
        Index("idx_telemetry_sanitization_state", "result_state", "created_at"),
    )

    sanitization_result_id: Mapped[str] = mapped_column(String, primary_key=True)
    telemetry_event_id: Mapped[str | None] = mapped_column(ForeignKey("telemetry_queue.telemetry_event_id"))
    telemetry_rejection_id: Mapped[str | None] = mapped_column(ForeignKey("telemetry_rejections.telemetry_rejection_id"))
    result_state: Mapped[str] = mapped_column(String, nullable=False)
    rules_applied_json: Mapped[list] = mapped_column(JSON, nullable=False)
    redaction_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class TelemetryDeliveryAttemptRecord(Base):
    __tablename__ = "telemetry_delivery_attempts"
    __table_args__ = (
        UniqueConstraint("telemetry_event_id", "attempt_number", name="uq_telemetry_delivery_event_attempt"),
        CheckConstraint("status in ('succeeded', 'failed', 'skipped')", name="ck_telemetry_delivery_status"),
        Index("idx_telemetry_delivery_event", "telemetry_event_id"),
        Index("idx_telemetry_delivery_status_time", "status", "attempted_at"),
    )

    delivery_attempt_id: Mapped[str] = mapped_column(String, primary_key=True)
    telemetry_event_id: Mapped[str] = mapped_column(ForeignKey("telemetry_queue.telemetry_event_id"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    attempted_at: Mapped[str] = mapped_column(String, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    error_summary: Mapped[str | None] = mapped_column(Text)


class ArtifactVersionRecord(Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (
        UniqueConstraint("platform", "build_number", name="uq_artifact_versions_platform_build"),
        CheckConstraint("platform in ('windows', 'linux')", name="ck_artifact_versions_platform"),
        CheckConstraint("channel in ('recommended', 'latest', 'optional', 'pinned')", name="ck_artifact_versions_channel"),
        Index("idx_artifact_versions_channel", "platform", "channel", "released_at"),
    )

    artifact_version_id: Mapped[str] = mapped_column(String, primary_key=True)
    platform: Mapped[str] = mapped_column(String, nullable=False)
    channel: Mapped[str] = mapped_column(String, nullable=False)
    build_number: Mapped[str] = mapped_column(String, nullable=False)
    download_url: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String)
    released_at: Mapped[str | None] = mapped_column(String)
    discovered_at: Mapped[str] = mapped_column(String, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)


class ProjectArtifactPinRecord(Base):
    __tablename__ = "project_artifact_pins"
    __table_args__ = (
        UniqueConstraint("project_id", "environment_id", name="uq_project_artifact_pins_project_environment"),
        CheckConstraint("channel_preference in ('recommended', 'latest', 'pinned')", name="ck_project_artifact_pins_channel"),
        Index("idx_project_artifact_pins_project", "project_id"),
    )

    artifact_pin_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    environment_id: Mapped[str | None] = mapped_column(ForeignKey("environment_profiles.environment_id"))
    artifact_version_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_versions.artifact_version_id"))
    channel_preference: Mapped[str] = mapped_column(String, nullable=False)
    pinned_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class SetupRecipeRecord(Base):
    __tablename__ = "setup_recipes"
    __table_args__ = (
        UniqueConstraint("recipe_slug", "recipe_version", name="uq_setup_recipes_slug_version"),
        CheckConstraint("source_type in ('builtin', 'plugin', 'local')", name="ck_setup_recipes_source_type"),
        Index("idx_setup_recipes_source", "source_type", "source_ref"),
    )

    setup_recipe_id: Mapped[str] = mapped_column(String, primary_key=True)
    recipe_slug: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String)
    recipe_version: Mapped[str] = mapped_column(String, nullable=False)
    definition_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class SetupRunRecord(Base):
    __tablename__ = "setup_runs"
    __table_args__ = (
        CheckConstraint("status in ('planned', 'running', 'succeeded', 'failed', 'cancelled')", name="ck_setup_runs_status"),
        CheckConstraint("dry_run in (0, 1)", name="ck_setup_runs_dry_run"),
        Index("idx_setup_runs_project_time", "project_id", "started_at"),
        Index("idx_setup_runs_status", "status"),
    )

    setup_run_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    environment_id: Mapped[str | None] = mapped_column(ForeignKey("environment_profiles.environment_id"))
    setup_recipe_id: Mapped[str | None] = mapped_column(ForeignKey("setup_recipes.setup_recipe_id"))
    status: Mapped[str] = mapped_column(String, nullable=False)
    dry_run: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[str | None] = mapped_column(String)
    finished_at: Mapped[str | None] = mapped_column(String)
    summary_json: Mapped[dict | None] = mapped_column(JSON)


class SetupRunStepRecord(Base):
    __tablename__ = "setup_run_steps"
    __table_args__ = (
        UniqueConstraint("setup_run_id", "step_order", name="uq_setup_run_steps_run_order"),
        Index("idx_setup_run_steps_run_status", "setup_run_id", "status"),
    )

    setup_step_id: Mapped[str] = mapped_column(String, primary_key=True)
    setup_run_id: Mapped[str] = mapped_column(ForeignKey("setup_runs.setup_run_id"), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    step_key: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[str | None] = mapped_column(String)
    finished_at: Mapped[str | None] = mapped_column(String)
    details_json: Mapped[dict | None] = mapped_column(JSON)


class DependencyCheckRecord(Base):
    __tablename__ = "dependency_checks"
    __table_args__ = (
        CheckConstraint("category in ('binary', 'database', 'config', 'network', 'filesystem')", name="ck_dependency_checks_category"),
        CheckConstraint("status in ('pass', 'warning', 'fail', 'skipped')", name="ck_dependency_checks_status"),
        Index("idx_dependency_checks_project_time", "project_id", "checked_at"),
        Index("idx_dependency_checks_status", "status"),
    )

    dependency_check_id: Mapped[str] = mapped_column(String, primary_key=True)
    setup_run_id: Mapped[str | None] = mapped_column(ForeignKey("setup_runs.setup_run_id"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    check_key: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    details_json: Mapped[dict | None] = mapped_column(JSON)
    checked_at: Mapped[str] = mapped_column(String, nullable=False)


class TxAdminInstanceRecord(Base):
    __tablename__ = "txadmin_instances"
    __table_args__ = (
        UniqueConstraint("project_id", "txdata_path_id", name="uq_txadmin_instances_project_txdata"),
        Index("idx_txadmin_instances_project", "project_id"),
    )

    txadmin_instance_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    txdata_path_id: Mapped[str | None] = mapped_column(ForeignKey("project_paths.project_path_id"))
    host: Mapped[str | None] = mapped_column(String)
    port: Mapped[int | None] = mapped_column(Integer)
    detected_version: Mapped[str | None] = mapped_column(String)
    last_seen_at: Mapped[str | None] = mapped_column(String)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)


class SetupProcessRunRecord(Base):
    __tablename__ = "setup_process_runs"
    __table_args__ = (
        CheckConstraint("state in ('starting', 'running', 'stopping', 'stopped', 'crashed')", name="ck_setup_process_runs_state"),
        Index("idx_setup_process_runs_project_time", "project_id", "started_at"),
        Index("idx_setup_process_runs_state", "state"),
    )

    process_run_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    pid: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String, nullable=False)
    launch_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    started_at: Mapped[str | None] = mapped_column(String)
    stopped_at: Mapped[str | None] = mapped_column(String)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    stdout_tail_json: Mapped[list | None] = mapped_column(JSON)
    stderr_tail_json: Mapped[list | None] = mapped_column(JSON)


class ConfigFileRecord(Base):
    __tablename__ = "config_files"
    __table_args__ = (
        UniqueConstraint("project_id", "environment_id", "path", name="uq_config_files_project_env_path"),
        CheckConstraint("config_type in ('server_cfg', 'resource', 'txadmin', 'database', 'unknown')", name="ck_config_files_type"),
        Index("idx_config_files_project_type", "project_id", "config_type"),
    )

    config_file_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    environment_id: Mapped[str | None] = mapped_column(ForeignKey("environment_profiles.environment_id"))
    path: Mapped[str] = mapped_column(Text, nullable=False)
    config_type: Mapped[str] = mapped_column(String, nullable=False)
    parser_kind: Mapped[str | None] = mapped_column(String)
    content_hash: Mapped[str | None] = mapped_column(String)
    last_scanned_at: Mapped[str | None] = mapped_column(String)


class ConfigSnapshotRecord(Base):
    __tablename__ = "config_snapshots"
    __table_args__ = (
        CheckConstraint("snapshot_kind in ('before', 'after', 'manual', 'validation')", name="ck_config_snapshots_kind"),
        Index("idx_config_snapshots_file_time", "config_file_id", "captured_at"),
    )

    config_snapshot_id: Mapped[str] = mapped_column(String, primary_key=True)
    config_file_id: Mapped[str] = mapped_column(ForeignKey("config_files.config_file_id"), nullable=False)
    snapshot_kind: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    local_file_id: Mapped[str | None] = mapped_column(String)
    captured_at: Mapped[str] = mapped_column(String, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)


class ConfigChangeSetRecord(Base):
    __tablename__ = "config_change_sets"
    __table_args__ = (
        CheckConstraint("status in ('planned', 'applied', 'reverted', 'failed')", name="ck_config_change_sets_status"),
        Index("idx_config_change_sets_project_time", "project_id", "created_at"),
    )

    config_change_set_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    command_execution_id: Mapped[str | None] = mapped_column(ForeignKey("command_executions.command_execution_id"))
    status: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    before_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("config_snapshots.config_snapshot_id"))
    after_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("config_snapshots.config_snapshot_id"))
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    applied_at: Mapped[str | None] = mapped_column(String)


class ConfigValidationRunRecord(Base):
    __tablename__ = "config_validation_runs"
    __table_args__ = (
        CheckConstraint("status in ('pass', 'warning', 'fail', 'error')", name="ck_config_validation_runs_status"),
        Index("idx_config_validation_project_time", "project_id", "started_at"),
        Index("idx_config_validation_status", "status"),
    )

    config_validation_run_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    config_file_id: Mapped[str | None] = mapped_column(ForeignKey("config_files.config_file_id"))
    validator_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[str] = mapped_column(String, nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String)
    summary_json: Mapped[dict | None] = mapped_column(JSON)


class ConfigValidationFindingRecord(Base):
    __tablename__ = "config_validation_findings"
    __table_args__ = (Index("idx_config_findings_run_severity", "config_validation_run_id", "severity"),)

    finding_id: Mapped[str] = mapped_column(String, primary_key=True)
    config_validation_run_id: Mapped[str] = mapped_column(ForeignKey("config_validation_runs.config_validation_run_id"), nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    rule_id: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str | None] = mapped_column(Text)
    line: Mapped[int | None] = mapped_column(Integer)
    column: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict | None] = mapped_column(JSON)


class SecretScanFindingRecord(Base):
    __tablename__ = "secret_scan_findings"
    __table_args__ = (
        CheckConstraint("status in ('open', 'ignored', 'resolved')", name="ck_secret_scan_findings_status"),
        Index("idx_secret_findings_project_status", "project_id", "status"),
    )

    secret_finding_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    config_file_id: Mapped[str | None] = mapped_column(ForeignKey("config_files.config_file_id"))
    detector_id: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str | None] = mapped_column(Text)
    line: Mapped[int | None] = mapped_column(Integer)
    redacted_preview: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, nullable=False)
    detected_at: Mapped[str] = mapped_column(String, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)


class GitRepositoryRecord(Base):
    __tablename__ = "git_repositories"
    __table_args__ = (
        UniqueConstraint("project_id", "local_path", name="uq_git_repositories_project_path"),
        CheckConstraint("repository_role in ('project', 'resource', 'template', 'unknown')", name="ck_git_repositories_role"),
        Index("idx_git_repositories_project_role", "project_id", "repository_role"),
    )

    git_repository_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    local_path: Mapped[str] = mapped_column(Text, nullable=False)
    remote_url: Mapped[str | None] = mapped_column(Text)
    default_branch: Mapped[str | None] = mapped_column(String)
    repository_role: Mapped[str] = mapped_column(String, nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String)
    last_scanned_at: Mapped[str | None] = mapped_column(String)


class GitRefRecord(Base):
    __tablename__ = "git_refs"
    __table_args__ = (
        UniqueConstraint("git_repository_id", "ref_name", "ref_type", name="uq_git_refs_repo_name_type"),
        CheckConstraint("ref_type in ('branch', 'tag', 'remote')", name="ck_git_refs_type"),
        Index("idx_git_refs_repo_current", "git_repository_id", "is_current"),
    )

    git_ref_id: Mapped[str] = mapped_column(String, primary_key=True)
    git_repository_id: Mapped[str] = mapped_column(ForeignKey("git_repositories.git_repository_id"), nullable=False)
    ref_name: Mapped[str] = mapped_column(Text, nullable=False)
    ref_type: Mapped[str] = mapped_column(String, nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String)
    is_current: Mapped[int] = mapped_column(Integer, nullable=False)
    detected_at: Mapped[str] = mapped_column(String, nullable=False)


class GitCommitRecord(Base):
    __tablename__ = "git_commits"
    __table_args__ = (
        UniqueConstraint("git_repository_id", "commit_sha", name="uq_git_commits_repo_sha"),
        Index("idx_git_commits_repo_time", "git_repository_id", "committed_at"),
    )

    git_commit_id: Mapped[str] = mapped_column(String, primary_key=True)
    git_repository_id: Mapped[str] = mapped_column(ForeignKey("git_repositories.git_repository_id"), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String, nullable=False)
    parent_shas_json: Mapped[list | None] = mapped_column(JSON)
    author_name: Mapped[str | None] = mapped_column(String)
    author_email_hash: Mapped[str | None] = mapped_column(String)
    committed_at: Mapped[str | None] = mapped_column(String)
    message_summary: Mapped[str | None] = mapped_column(Text)


class GitWorktreeStatusSnapshotRecord(Base):
    __tablename__ = "git_worktree_status_snapshots"
    __table_args__ = (
        CheckConstraint("is_dirty in (0, 1)", name="ck_git_status_dirty"),
        Index("idx_git_status_repo_time", "git_repository_id", "captured_at"),
        Index("idx_git_status_dirty", "is_dirty", "captured_at"),
    )

    git_status_snapshot_id: Mapped[str] = mapped_column(String, primary_key=True)
    git_repository_id: Mapped[str] = mapped_column(ForeignKey("git_repositories.git_repository_id"), nullable=False)
    head_commit_sha: Mapped[str | None] = mapped_column(String)
    branch_name: Mapped[str | None] = mapped_column(String)
    is_dirty: Mapped[int] = mapped_column(Integer, nullable=False)
    ahead_count: Mapped[int | None] = mapped_column(Integer)
    behind_count: Mapped[int | None] = mapped_column(Integer)
    captured_at: Mapped[str] = mapped_column(String, nullable=False)
    summary_json: Mapped[dict | None] = mapped_column(JSON)


class GitFileChangeRecord(Base):
    __tablename__ = "git_file_changes"
    __table_args__ = (
        UniqueConstraint("git_status_snapshot_id", "path", name="uq_git_file_changes_snapshot_path"),
        Index("idx_git_file_changes_status", "change_status"),
        CheckConstraint(
            "change_status in ('added', 'modified', 'deleted', 'renamed', 'untracked')",
            name="ck_git_file_changes_status",
        ),
    )

    git_file_change_id: Mapped[str] = mapped_column(String, primary_key=True)
    git_status_snapshot_id: Mapped[str] = mapped_column(ForeignKey("git_worktree_status_snapshots.git_status_snapshot_id"), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    change_status: Mapped[str] = mapped_column(String, nullable=False)
    old_path: Mapped[str | None] = mapped_column(Text)
    insertions: Mapped[int | None] = mapped_column(Integer)
    deletions: Mapped[int | None] = mapped_column(Integer)


class GitOperationRecord(Base):
    __tablename__ = "git_operations"
    __table_args__ = (
        CheckConstraint(
            "operation_type in ('clone', 'fetch', 'pull', 'checkout', 'commit', 'diff', 'status')",
            name="ck_git_operations_type",
        ),
        CheckConstraint("status in ('planned', 'running', 'succeeded', 'failed', 'cancelled')", name="ck_git_operations_status"),
        Index("idx_git_operations_repo_time", "git_repository_id", "started_at"),
        Index("idx_git_operations_status", "status"),
    )

    git_operation_id: Mapped[str] = mapped_column(String, primary_key=True)
    git_repository_id: Mapped[str] = mapped_column(ForeignKey("git_repositories.git_repository_id"), nullable=False)
    operation_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    command_execution_id: Mapped[str | None] = mapped_column(ForeignKey("command_executions.command_execution_id"))
    started_at: Mapped[str | None] = mapped_column(String)
    finished_at: Mapped[str | None] = mapped_column(String)
    result_json: Mapped[dict | None] = mapped_column(JSON)
