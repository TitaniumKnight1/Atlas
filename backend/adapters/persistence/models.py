from __future__ import annotations

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
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


class ResourceRecord(Base):
    __tablename__ = "resources"
    __table_args__ = (
        UniqueConstraint("project_id", "resource_name", name="uq_resources_project_name"),
        CheckConstraint("enabled_state in ('enabled', 'disabled', 'unknown')", name="ck_resources_enabled_state"),
        CheckConstraint("resource_type in ('script', 'map', 'framework', 'library', 'unknown')", name="ck_resources_type"),
        Index("idx_resources_project_state", "project_id", "enabled_state"),
        Index("idx_resources_startup", "project_id", "startup_order"),
    )

    resource_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    resource_name: Mapped[str] = mapped_column(Text, nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str] = mapped_column(String, nullable=False)
    enabled_state: Mapped[str] = mapped_column(String, nullable=False)
    startup_order: Mapped[int | None] = mapped_column(Integer)
    current_version_id: Mapped[str | None] = mapped_column(String)
    git_repository_id: Mapped[str | None] = mapped_column(ForeignKey("git_repositories.git_repository_id"))
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class ResourceVersionRecord(Base):
    __tablename__ = "resource_versions"
    __table_args__ = (
        UniqueConstraint("resource_id", "content_hash", name="uq_resource_versions_resource_hash"),
        Index("idx_resource_versions_resource_time", "resource_id", "detected_at"),
    )

    resource_version_id: Mapped[str] = mapped_column(String, primary_key=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.resource_id"), nullable=False)
    version_label: Mapped[str | None] = mapped_column(String)
    git_commit_sha: Mapped[str | None] = mapped_column(String)
    source_ref: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String)
    manifest_json: Mapped[dict | None] = mapped_column(JSON)
    detected_at: Mapped[str] = mapped_column(String, nullable=False)


class ResourceDependencyRecord(Base):
    __tablename__ = "resource_dependencies"
    __table_args__ = (
        UniqueConstraint("source_resource_id", "target_name", "dependency_type", name="uq_resource_dependencies_source_target_type"),
        CheckConstraint("dependency_type in ('requires', 'optional', 'conflicts', 'loads_after')", name="ck_resource_dependencies_type"),
        Index("idx_resource_dependencies_project", "project_id"),
        Index("idx_resource_dependencies_target", "target_resource_id"),
    )

    resource_dependency_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    source_resource_id: Mapped[str] = mapped_column(ForeignKey("resources.resource_id"), nullable=False)
    target_resource_id: Mapped[str | None] = mapped_column(ForeignKey("resources.resource_id"))
    target_name: Mapped[str] = mapped_column(Text, nullable=False)
    dependency_type: Mapped[str] = mapped_column(String, nullable=False)
    declared_in_path: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[str] = mapped_column(String, nullable=False)


class ResourceStateChangeRecord(Base):
    __tablename__ = "resource_state_changes"
    __table_args__ = (
        CheckConstraint(
            "change_type in ('install', 'update', 'enable', 'disable', 'delete', 'rollback')",
            name="ck_resource_state_changes_type",
        ),
        Index("idx_resource_state_changes_resource_time", "resource_id", "changed_at"),
    )

    resource_state_change_id: Mapped[str] = mapped_column(String, primary_key=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.resource_id"), nullable=False)
    change_type: Mapped[str] = mapped_column(String, nullable=False)
    from_state: Mapped[str | None] = mapped_column(String)
    to_state: Mapped[str | None] = mapped_column(String)
    command_execution_id: Mapped[str | None] = mapped_column(ForeignKey("command_executions.command_execution_id"))
    audit_event_id: Mapped[str | None] = mapped_column(ForeignKey("audit_events.audit_event_id"))
    changed_at: Mapped[str] = mapped_column(String, nullable=False)
    details_json: Mapped[dict | None] = mapped_column(JSON)


class ResourceHealthSnapshotRecord(Base):
    __tablename__ = "resource_health_snapshots"
    __table_args__ = (
        CheckConstraint("health_status in ('healthy', 'warning', 'error', 'unknown')", name="ck_resource_health_status"),
        Index("idx_resource_health_resource_time", "resource_id", "sampled_at"),
        Index("idx_resource_health_status", "health_status"),
    )

    resource_health_snapshot_id: Mapped[str] = mapped_column(String, primary_key=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.resource_id"), nullable=False)
    environment_id: Mapped[str | None] = mapped_column(String)
    health_status: Mapped[str] = mapped_column(String, nullable=False)
    server_fps: Mapped[float | None] = mapped_column(Float)
    cpu_percent: Mapped[float | None] = mapped_column(Float)
    memory_mb: Mapped[float | None] = mapped_column(Float)
    sampled_at: Mapped[str] = mapped_column(String, nullable=False)
    details_json: Mapped[dict | None] = mapped_column(JSON)


class ResourceInstallSourceRecord(Base):
    __tablename__ = "resource_install_sources"
    __table_args__ = (
        UniqueConstraint("resource_id", "source_type", "source_uri", name="uq_resource_install_sources_resource_type_uri"),
        CheckConstraint("source_type in ('git', 'zip', 'local', 'plugin', 'manual')", name="ck_resource_install_sources_type"),
        Index("idx_resource_install_sources_type", "source_type"),
    )

    resource_install_source_id: Mapped[str] = mapped_column(String, primary_key=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.resource_id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_uri: Mapped[str | None] = mapped_column(Text)
    plugin_id: Mapped[str | None] = mapped_column(String)
    trusted_at: Mapped[str | None] = mapped_column(String)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)


class ResourceRollbackRunRecord(Base):
    __tablename__ = "resource_rollback_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('planned', 'running', 'completed', 'halted', 'refused')",
            name="ck_resource_rollback_runs_status",
        ),
        Index("idx_resource_rollback_runs_project_time", "project_id", "started_at"),
    )

    resource_rollback_run_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    plan_json: Mapped[dict | None] = mapped_column(JSON)
    result_json: Mapped[dict | None] = mapped_column(JSON)
    command_execution_id: Mapped[str | None] = mapped_column(ForeignKey("command_executions.command_execution_id"))
    started_at: Mapped[str] = mapped_column(String, nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String)


class ResourceRollbackOutcomeRecord(Base):
    __tablename__ = "resource_rollback_outcomes"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'succeeded', 'failed', 'not_attempted')",
            name="ck_resource_rollback_outcomes_status",
        ),
        Index("idx_resource_rollback_outcomes_run", "resource_rollback_run_id", "position"),
    )

    resource_rollback_outcome_id: Mapped[str] = mapped_column(String, primary_key=True)
    resource_rollback_run_id: Mapped[str] = mapped_column(ForeignKey("resource_rollback_runs.resource_rollback_run_id"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String)
    resource_name: Mapped[str] = mapped_column(Text, nullable=False)
    command_execution_id: Mapped[str | None] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    outcome_json: Mapped[dict | None] = mapped_column(JSON)


class MetricSourceRecord(Base):
    __tablename__ = "metric_sources"
    __table_args__ = (
        CheckConstraint(
            "source_type in ('process', 'resource', 'database', 'network', 'disk', 'plugin', 'system', 'deferred')",
            name="ck_metric_sources_type",
        ),
        UniqueConstraint("project_id", "source_type", "source_ref", name="uq_metric_sources_project_type_ref"),
        Index("idx_metric_sources_project_enabled", "project_id", "is_enabled"),
    )

    metric_source_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    environment_id: Mapped[str | None] = mapped_column(String)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)


class MetricSeriesRecord(Base):
    __tablename__ = "metric_series"
    __table_args__ = (
        CheckConstraint("value_type in ('gauge', 'counter', 'status')", name="ck_metric_series_value_type"),
        CheckConstraint("retention_class in ('high', 'standard', 'long')", name="ck_metric_series_retention"),
        UniqueConstraint("metric_source_id", "metric_name", name="uq_metric_series_source_name"),
        Index("idx_metric_series_name", "metric_name"),
    )

    metric_series_id: Mapped[str] = mapped_column(String, primary_key=True)
    metric_source_id: Mapped[str] = mapped_column(ForeignKey("metric_sources.metric_source_id"), nullable=False)
    metric_name: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String, nullable=False)
    retention_class: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class MetricSampleRecord(Base):
    __tablename__ = "metric_samples"
    __table_args__ = (
        CheckConstraint("quality in ('ok', 'estimated', 'missing')", name="ck_metric_samples_quality"),
        UniqueConstraint("metric_series_id", "sampled_at", name="uq_metric_samples_series_time"),
        Index("idx_metric_samples_series_time", "metric_series_id", "sampled_at"),
    )

    sample_id: Mapped[str] = mapped_column(String, primary_key=True)
    metric_series_id: Mapped[str] = mapped_column(ForeignKey("metric_series.metric_series_id"), nullable=False)
    sampled_at: Mapped[str] = mapped_column(String, nullable=False)
    value_real: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(Text)
    quality: Mapped[str] = mapped_column(String, nullable=False)


class MetricRollupRecord(Base):
    __tablename__ = "metric_rollups"
    __table_args__ = (
        UniqueConstraint("metric_series_id", "bucket_start", "bucket_size_seconds", name="uq_metric_rollups_series_bucket"),
        Index("idx_metric_rollups_series_bucket", "metric_series_id", "bucket_size_seconds", "bucket_start"),
        Index("idx_metric_rollups_project_bucket", "project_id", "bucket_size_seconds", "bucket_start"),
    )

    rollup_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    metric_series_id: Mapped[str] = mapped_column(ForeignKey("metric_series.metric_series_id"), nullable=False)
    bucket_start: Mapped[str] = mapped_column(String, nullable=False)
    bucket_size_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    min_value: Mapped[float | None] = mapped_column(Float)
    max_value: Mapped[float | None] = mapped_column(Float)
    sum_value: Mapped[float | None] = mapped_column(Float)
    avg_value: Mapped[float | None] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)


class MetricRollupWatermarkRecord(Base):
    __tablename__ = "metric_rollup_watermarks"
    __table_args__ = (
        UniqueConstraint("project_id", "tier", name="uq_metric_rollup_watermarks_project_tier"),
    )

    watermark_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    tier: Mapped[str] = mapped_column(String, nullable=False)
    watermark_bucket_end: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class MonitoringAlertRecord(Base):
    __tablename__ = "monitoring_alerts"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_monitoring_alerts_project_name"),
        CheckConstraint("runtime_state in ('ok', 'pending', 'firing')", name="ck_monitoring_alerts_runtime_state"),
        Index("idx_monitoring_alerts_enabled", "project_id", "is_enabled"),
    )

    monitoring_alert_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    metric_series_id: Mapped[str | None] = mapped_column(ForeignKey("metric_series.metric_series_id"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    condition_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_enabled: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime_state: Mapped[str] = mapped_column(String, nullable=False, default="ok")
    pending_since: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class MonitoringAlertEventRecord(Base):
    __tablename__ = "monitoring_alert_events"
    __table_args__ = (
        CheckConstraint("status in ('triggered', 'resolved', 'suppressed')", name="ck_monitoring_alert_events_status"),
        Index("idx_monitoring_alert_events_project_time", "project_id", "triggered_at"),
        Index("idx_monitoring_alert_events_status", "status"),
    )

    alert_event_id: Mapped[str] = mapped_column(String, primary_key=True)
    monitoring_alert_id: Mapped[str] = mapped_column(ForeignKey("monitoring_alerts.monitoring_alert_id"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    triggered_at: Mapped[str] = mapped_column(String, nullable=False)
    resolved_at: Mapped[str | None] = mapped_column(String)
    incident_group_id: Mapped[str | None] = mapped_column(String)
    details_json: Mapped[dict | None] = mapped_column(JSON)


class IncidentGroupRecord(Base):
    __tablename__ = "incident_groups"
    __table_args__ = (
        UniqueConstraint("project_id", "fingerprint", name="uq_incident_groups_project_fingerprint"),
        CheckConstraint("severity in ('debug', 'info', 'warning', 'error', 'fatal')", name="ck_incident_groups_severity"),
        CheckConstraint(
            "category in ('crash', 'startup', 'resource', 'validation', 'database', 'automation', 'plugin', 'atlas')",
            name="ck_incident_groups_category",
        ),
        CheckConstraint("status in ('unresolved', 'resolved', 'ignored', 'muted')", name="ck_incident_groups_status"),
        Index("idx_incident_groups_project_status_last_seen", "project_id", "status", "last_seen_at"),
        Index("idx_incident_groups_severity", "severity"),
    )

    incident_group_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    first_seen_at: Mapped[str] = mapped_column(String, nullable=False)
    last_seen_at: Mapped[str] = mapped_column(String, nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(String)


class IncidentOccurrenceRecord(Base):
    __tablename__ = "incident_occurrences"
    __table_args__ = (
        CheckConstraint(
            "source_type in ('log', 'process', 'validation', 'automation', 'plugin', 'manual')",
            name="ck_incident_occurrences_source_type",
        ),
        Index("idx_incident_occurrences_group_time", "incident_group_id", "occurred_at"),
        Index("idx_incident_occurrences_project_time", "project_id", "occurred_at"),
    )

    occurrence_id: Mapped[str] = mapped_column(String, primary_key=True)
    incident_group_id: Mapped[str] = mapped_column(ForeignKey("incident_groups.incident_group_id"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    environment_id: Mapped[str | None] = mapped_column(String)
    occurred_at: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_message_hash: Mapped[str | None] = mapped_column(Text)
    artifact_version_id: Mapped[str | None] = mapped_column(String)
    git_status_snapshot_id: Mapped[str | None] = mapped_column(String)
    automation_run_id: Mapped[str | None] = mapped_column(String)
    resource_id: Mapped[str | None] = mapped_column(String)


class IncidentBreadcrumbRecord(Base):
    __tablename__ = "incident_breadcrumbs"
    __table_args__ = (
        CheckConstraint(
            "category in ('server', 'resource', 'git', 'config', 'automation', 'process', 'log')",
            name="ck_incident_breadcrumbs_category",
        ),
        CheckConstraint("level in ('debug', 'info', 'warning', 'error', 'fatal')", name="ck_incident_breadcrumbs_level"),
        UniqueConstraint("occurrence_id", "sort_order", name="uq_incident_breadcrumbs_occurrence_order"),
        Index("idx_incident_breadcrumbs_occurrence_time", "occurrence_id", "timestamp"),
    )

    breadcrumb_id: Mapped[str] = mapped_column(String, primary_key=True)
    occurrence_id: Mapped[str] = mapped_column(ForeignKey("incident_occurrences.occurrence_id"), nullable=False)
    timestamp: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data_json: Mapped[dict | None] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class IncidentContextSnapshotRecord(Base):
    __tablename__ = "incident_context_snapshots"
    __table_args__ = (
        CheckConstraint(
            "context_type in ('environment', 'runtime', 'resources', 'startup_order', 'config_excerpt', 'logs', 'database', 'system')",
            name="ck_incident_context_type",
        ),
        CheckConstraint(
            "redaction_state in ('raw_local', 'redacted', 'export_safe', 'blocked')",
            name="ck_incident_context_redaction_state",
        ),
        Index("idx_incident_context_occurrence_type", "occurrence_id", "context_type"),
    )

    context_snapshot_id: Mapped[str] = mapped_column(String, primary_key=True)
    occurrence_id: Mapped[str] = mapped_column(ForeignKey("incident_occurrences.occurrence_id"), nullable=False)
    context_type: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(Text)
    local_file_id: Mapped[str | None] = mapped_column(String)
    snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    redaction_state: Mapped[str] = mapped_column(String, nullable=False)
    captured_at: Mapped[str] = mapped_column(String, nullable=False)


class IncidentStackTraceRecord(Base):
    __tablename__ = "incident_stack_traces"
    __table_args__ = (Index("idx_incident_stack_traces_occurrence", "occurrence_id"),)

    stack_trace_id: Mapped[str] = mapped_column(String, primary_key=True)
    occurrence_id: Mapped[str] = mapped_column(ForeignKey("incident_occurrences.occurrence_id"), nullable=False)
    exception_type: Mapped[str | None] = mapped_column(Text)
    exception_value: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String)
    thread_name: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[int] = mapped_column(Integer, nullable=False)


class IncidentFingerprintRecord(Base):
    __tablename__ = "incident_fingerprints"
    __table_args__ = (
        UniqueConstraint("incident_group_id", "fingerprint", "algorithm_version", name="uq_incident_fingerprints_group_fp_algo"),
        Index("idx_incident_fingerprints_active", "fingerprint", "is_active"),
    )

    incident_fingerprint_id: Mapped[str] = mapped_column(String, primary_key=True)
    incident_group_id: Mapped[str] = mapped_column(ForeignKey("incident_groups.incident_group_id"), nullable=False)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String, nullable=False)
    components_json: Mapped[dict | None] = mapped_column(JSON)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class IncidentStackFrameRecord(Base):
    __tablename__ = "incident_stack_frames"
    __table_args__ = (
        UniqueConstraint("stack_trace_id", "frame_index", name="uq_incident_stack_frames_trace_index"),
        Index("idx_incident_stack_frames_trace_index", "stack_trace_id", "frame_index"),
        Index("idx_incident_stack_frames_hash", "frame_hash"),
    )

    stack_frame_id: Mapped[str] = mapped_column(String, primary_key=True)
    stack_trace_id: Mapped[str] = mapped_column(ForeignKey("incident_stack_traces.stack_trace_id"), nullable=False)
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    function_name: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)
    line_number: Mapped[int | None] = mapped_column(Integer)
    column_number: Mapped[int | None] = mapped_column(Integer)
    resource_id: Mapped[str | None] = mapped_column(String)
    in_app: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frame_hash: Mapped[str | None] = mapped_column(Text)


class IncidentRelatedGroupRecord(Base):
    __tablename__ = "incident_related_groups"
    __table_args__ = (
        UniqueConstraint("source_group_id", "target_group_id", "relation_type", name="uq_incident_related_groups"),
        Index("idx_incident_related_source", "source_group_id"),
        Index("idx_incident_related_target", "target_group_id"),
    )

    incident_relation_id: Mapped[str] = mapped_column(String, primary_key=True)
    source_group_id: Mapped[str] = mapped_column(ForeignKey("incident_groups.incident_group_id"), nullable=False)
    target_group_id: Mapped[str] = mapped_column(ForeignKey("incident_groups.incident_group_id"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float | None] = mapped_column()
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class IncidentGroupRuleRecord(Base):
    __tablename__ = "incident_group_rules"
    __table_args__ = (Index("idx_incident_group_rules_project_enabled", "project_id", "is_enabled"),)

    incident_group_rule_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    rule_type: Mapped[str] = mapped_column(String, nullable=False)
    match_json: Mapped[dict | None] = mapped_column(JSON)
    action_json: Mapped[dict | None] = mapped_column(JSON)
    is_enabled: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class IncidentNoteRecord(Base):
    __tablename__ = "incident_notes"
    __table_args__ = (Index("idx_incident_notes_group_time", "incident_group_id", "created_at"),)

    incident_note_id: Mapped[str] = mapped_column(String, primary_key=True)
    incident_group_id: Mapped[str] = mapped_column(ForeignKey("incident_groups.incident_group_id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str | None] = mapped_column(String)
    created_by: Mapped[str | None] = mapped_column(String)


class IncidentExportRecord(Base):
    __tablename__ = "incident_exports"
    __table_args__ = (Index("idx_incident_exports_group_time", "incident_group_id", "created_at"),)

    incident_export_id: Mapped[str] = mapped_column(String, primary_key=True)
    incident_group_id: Mapped[str] = mapped_column(ForeignKey("incident_groups.incident_group_id"), nullable=False)
    occurrence_id: Mapped[str | None] = mapped_column(String)
    export_format: Mapped[str] = mapped_column(String, nullable=False)
    redaction_profile: Mapped[str] = mapped_column(String, nullable=False)
    local_file_path: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    warning_json: Mapped[dict | None] = mapped_column(JSON)


class AutomationWorkflowRecord(Base):
    __tablename__ = "automation_workflows"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_automation_workflows_project_name"),
        Index("idx_automation_workflows_project_enabled", "project_id", "is_enabled"),
    )

    automation_workflow_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_enabled: Mapped[int] = mapped_column(Integer, nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class AutomationWorkflowVersionRecord(Base):
    __tablename__ = "automation_workflow_versions"
    __table_args__ = (
        UniqueConstraint("automation_workflow_id", "version_number", name="uq_automation_versions_workflow_number"),
        Index("idx_automation_versions_workflow", "automation_workflow_id"),
    )

    automation_workflow_version_id: Mapped[str] = mapped_column(String, primary_key=True)
    automation_workflow_id: Mapped[str] = mapped_column(ForeignKey("automation_workflows.automation_workflow_id"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class AutomationTriggerRecord(Base):
    __tablename__ = "automation_triggers"
    __table_args__ = (Index("idx_automation_triggers_version", "automation_workflow_version_id"),)

    automation_trigger_id: Mapped[str] = mapped_column(String, primary_key=True)
    automation_workflow_version_id: Mapped[str] = mapped_column(
        ForeignKey("automation_workflow_versions.automation_workflow_version_id"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String, nullable=False)
    config_json: Mapped[dict | None] = mapped_column(JSON)


class AutomationConditionRecord(Base):
    __tablename__ = "automation_conditions"
    __table_args__ = (Index("idx_automation_conditions_version", "automation_workflow_version_id", "position"),)

    automation_condition_id: Mapped[str] = mapped_column(String, primary_key=True)
    automation_workflow_version_id: Mapped[str] = mapped_column(
        ForeignKey("automation_workflow_versions.automation_workflow_version_id"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    condition_type: Mapped[str] = mapped_column(String, nullable=False)
    config_json: Mapped[dict | None] = mapped_column(JSON)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class AutomationActionRecord(Base):
    __tablename__ = "automation_actions"
    __table_args__ = (Index("idx_automation_actions_version", "automation_workflow_version_id", "position"),)

    automation_action_id: Mapped[str] = mapped_column(String, primary_key=True)
    automation_workflow_version_id: Mapped[str] = mapped_column(
        ForeignKey("automation_workflow_versions.automation_workflow_version_id"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    safety_class: Mapped[str] = mapped_column(String, nullable=False)
    config_json: Mapped[dict | None] = mapped_column(JSON)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class AutomationScheduleRecord(Base):
    __tablename__ = "automation_schedules"
    __table_args__ = (Index("idx_automation_schedules_due", "is_enabled", "next_run_at"),)

    automation_schedule_id: Mapped[str] = mapped_column(String, primary_key=True)
    automation_workflow_id: Mapped[str] = mapped_column(ForeignKey("automation_workflows.automation_workflow_id"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    schedule_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    next_run_at: Mapped[str] = mapped_column(String, nullable=False)
    last_run_at: Mapped[str | None] = mapped_column(String)
    is_enabled: Mapped[int] = mapped_column(Integer, nullable=False)


class AutomationRunRecord(Base):
    __tablename__ = "automation_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_automation_runs_idempotency"),
        CheckConstraint(
            "status in ('queued', 'running', 'waiting_approval', 'succeeded', 'failed', 'cancelled', 'skipped')",
            name="ck_automation_runs_status",
        ),
        Index("idx_automation_runs_project_time", "project_id", "started_at"),
        Index("idx_automation_runs_workflow", "automation_workflow_id"),
    )

    automation_run_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    automation_workflow_id: Mapped[str] = mapped_column(ForeignKey("automation_workflows.automation_workflow_id"), nullable=False)
    automation_workflow_version_id: Mapped[str] = mapped_column(
        ForeignKey("automation_workflow_versions.automation_workflow_version_id"), nullable=False
    )
    trigger_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    trigger_payload_json: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[str] = mapped_column(String, nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String)
    summary: Mapped[str | None] = mapped_column(Text)


class AutomationRunStepRecord(Base):
    __tablename__ = "automation_run_steps"
    __table_args__ = (Index("idx_automation_run_steps_run", "automation_run_id", "position"),)

    automation_run_step_id: Mapped[str] = mapped_column(String, primary_key=True)
    automation_run_id: Mapped[str] = mapped_column(ForeignKey("automation_runs.automation_run_id"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    automation_action_id: Mapped[str] = mapped_column(ForeignKey("automation_actions.automation_action_id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSON)
    undo_plan_json: Mapped[dict | None] = mapped_column(JSON)
    command_execution_id: Mapped[str | None] = mapped_column(ForeignKey("command_executions.command_execution_id"))


class AutomationIdempotencyKeyRecord(Base):
    __tablename__ = "automation_idempotency_keys"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_automation_idempotency_keys_key"),)

    automation_idempotency_key_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    automation_run_id: Mapped[str] = mapped_column(ForeignKey("automation_runs.automation_run_id"), nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class AutomationSettingRecord(Base):
    __tablename__ = "automation_settings"

    setting_key: Mapped[str] = mapped_column(String, primary_key=True)
    setting_value_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class AutomationApprovalRecord(Base):
    __tablename__ = "automation_approvals"
    __table_args__ = (
        CheckConstraint(
            "approval_state in ('pending', 'approved', 'denied', 'expired')",
            name="ck_automation_approvals_state",
        ),
        Index("idx_automation_approvals_pending", "approval_state", "requested_at"),
        Index("idx_automation_approvals_run", "automation_run_id"),
    )

    automation_approval_id: Mapped[str] = mapped_column(String, primary_key=True)
    automation_run_id: Mapped[str] = mapped_column(ForeignKey("automation_runs.automation_run_id"), nullable=False)
    automation_run_step_id: Mapped[str] = mapped_column(ForeignKey("automation_run_steps.automation_run_step_id"), nullable=False)
    automation_action_id: Mapped[str] = mapped_column(ForeignKey("automation_actions.automation_action_id"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    approval_state: Mapped[str] = mapped_column(String, nullable=False)
    preview_json: Mapped[dict | None] = mapped_column(JSON)
    requested_at: Mapped[str] = mapped_column(String, nullable=False)
    decided_at: Mapped[str | None] = mapped_column(String)
    decided_by: Mapped[str | None] = mapped_column(String)
    approval_reason: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[str | None] = mapped_column(String)


class AutomationRecipeInstanceRecord(Base):
    __tablename__ = "automation_recipe_instances"
    __table_args__ = (
        UniqueConstraint("project_id", "recipe_key", name="uq_automation_recipe_instances_project_key"),
        Index("idx_automation_recipe_instances_project", "project_id"),
    )

    automation_recipe_instance_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    recipe_key: Mapped[str] = mapped_column(String, nullable=False)
    automation_workflow_id: Mapped[str] = mapped_column(ForeignKey("automation_workflows.automation_workflow_id"), nullable=False)
    params_json: Mapped[dict | None] = mapped_column(JSON)
    instance_status: Mapped[str] = mapped_column(String, nullable=False)
    deferred_capabilities_json: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class BackupPlanRecord(Base):
    __tablename__ = "backup_plans"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_backup_plans_project_name"),
        CheckConstraint("backup_scope in ('config', 'resources', 'database', 'full', 'custom')", name="ck_backup_plans_scope"),
        Index("idx_backup_plans_project_enabled", "project_id", "is_enabled"),
        Index("idx_backup_plans_due", "is_enabled", "next_run_at"),
    )

    backup_plan_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    environment_id: Mapped[str | None] = mapped_column(String)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    backup_scope: Mapped[str] = mapped_column(String, nullable=False)
    schedule_id: Mapped[str | None] = mapped_column(String)
    retention_policy_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    schedule_interval_seconds: Mapped[int | None] = mapped_column(Integer)
    next_run_at: Mapped[str | None] = mapped_column(String)
    last_run_at: Mapped[str | None] = mapped_column(String)
    is_enabled: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class BackupRunRecord(Base):
    __tablename__ = "backup_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_backup_runs_idempotency"),
        CheckConstraint(
            "status in ('planned', 'running', 'succeeded', 'failed', 'cancelled', 'pruned')",
            name="ck_backup_runs_status",
        ),
        CheckConstraint(
            "trigger_type in ('manual', 'scheduled', 'pre_change', 'automation')",
            name="ck_backup_runs_trigger_type",
        ),
        Index("idx_backup_runs_project_time", "project_id", "started_at"),
        Index("idx_backup_runs_status", "status"),
    )

    backup_run_id: Mapped[str] = mapped_column(String, primary_key=True)
    backup_plan_id: Mapped[str | None] = mapped_column(ForeignKey("backup_plans.backup_plan_id"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String)
    artifact_version_id: Mapped[str | None] = mapped_column(String)
    git_status_snapshot_id: Mapped[str | None] = mapped_column(String)
    started_at: Mapped[str | None] = mapped_column(String)
    finished_at: Mapped[str | None] = mapped_column(String)
    total_bytes: Mapped[int | None] = mapped_column(Integer)
    archive_path: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(Text)
    manifest_json: Mapped[dict | None] = mapped_column(JSON)


class BackupItemRecord(Base):
    __tablename__ = "backup_items"
    __table_args__ = (Index("idx_backup_items_run_type", "backup_run_id", "item_type"),)

    backup_item_id: Mapped[str] = mapped_column(String, primary_key=True)
    backup_run_id: Mapped[str] = mapped_column(ForeignKey("backup_runs.backup_run_id"), nullable=False)
    item_type: Mapped[str] = mapped_column(String, nullable=False)
    source_path: Mapped[str | None] = mapped_column(Text)
    local_file_id: Mapped[str | None] = mapped_column(String)
    content_hash: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)


class BackupRestoreRunRecord(Base):
    __tablename__ = "backup_restore_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('planned', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_backup_restore_runs_status",
        ),
        Index("idx_backup_restore_project_time", "project_id", "started_at"),
    )

    restore_run_id: Mapped[str] = mapped_column(String, primary_key=True)
    backup_run_id: Mapped[str] = mapped_column(ForeignKey("backup_runs.backup_run_id"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    dry_run: Mapped[int] = mapped_column(Integer, nullable=False)
    command_execution_id: Mapped[str | None] = mapped_column(ForeignKey("command_executions.command_execution_id"))
    started_at: Mapped[str | None] = mapped_column(String)
    finished_at: Mapped[str | None] = mapped_column(String)
    restore_plan_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    pre_restore_snapshot_path: Mapped[str | None] = mapped_column(Text)
    undo_plan_json: Mapped[dict | None] = mapped_column(JSON)


class BackupRetentionEventRecord(Base):
    __tablename__ = "backup_retention_events"
    __table_args__ = (
        CheckConstraint("event_type in ('evaluated', 'pruned', 'skipped', 'failed')", name="ck_backup_retention_event_type"),
        Index("idx_backup_retention_project_time", "project_id", "occurred_at"),
    )

    retention_event_id: Mapped[str] = mapped_column(String, primary_key=True)
    backup_plan_id: Mapped[str | None] = mapped_column(ForeignKey("backup_plans.backup_plan_id"))
    backup_run_id: Mapped[str | None] = mapped_column(ForeignKey("backup_runs.backup_run_id"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[str] = mapped_column(String, nullable=False)
    details_json: Mapped[dict | None] = mapped_column(JSON)


class PluginSettingRecord(Base):
    __tablename__ = "plugin_settings"

    setting_key: Mapped[str] = mapped_column(String, primary_key=True)
    setting_value_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class PluginRegistrationRecord(Base):
    """App-global plugin registry — installations are not project-scoped."""

    __tablename__ = "plugin_registrations"
    __table_args__ = (
        UniqueConstraint("plugin_key", name="uq_plugin_registrations_plugin_key"),
        CheckConstraint(
            "registration_status in ('registered', 'disabled', 'restricted')",
            name="ck_plugin_registrations_status",
        ),
        CheckConstraint(
            "trust_status in ('pending_consent', 'consented', 'denied', 'revoked')",
            name="ck_plugin_registrations_trust_status",
        ),
        Index("idx_plugin_registrations_enabled", "is_enabled"),
    )

    plugin_id: Mapped[str] = mapped_column(String, primary_key=True)
    plugin_key: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text)
    contribution_points_json: Mapped[list] = mapped_column(JSON, nullable=False)
    requested_capabilities_json: Mapped[list] = mapped_column(JSON, nullable=False)
    registration_status: Mapped[str] = mapped_column(String, nullable=False)
    trust_status: Mapped[str] = mapped_column(String, nullable=False)
    is_enabled: Mapped[int] = mapped_column(Integer, nullable=False)
    registered_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class PluginCapabilityGrantRecord(Base):
    """Capability grants — project_id NULL means app-global grant."""

    __tablename__ = "plugin_capability_grants"
    __table_args__ = (
        UniqueConstraint("plugin_id", "project_id", "capability", name="uq_plugin_capability_grants_scope"),
        Index("idx_plugin_capability_grants_plugin", "plugin_id", "is_active"),
        Index("idx_plugin_capability_grants_project", "project_id", "is_active"),
    )

    grant_id: Mapped[str] = mapped_column(String, primary_key=True)
    plugin_id: Mapped[str] = mapped_column(ForeignKey("plugin_registrations.plugin_id"), nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.project_id"))
    capability: Mapped[str] = mapped_column(String, nullable=False)
    scope_json: Mapped[dict | None] = mapped_column(JSON)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False)
    granted_at: Mapped[str] = mapped_column(String, nullable=False)
    revoked_at: Mapped[str | None] = mapped_column(String)


class PluginTrustRecord(Base):
    """Explicit user consent records — per plugin, optionally per project."""

    __tablename__ = "plugin_trust_records"
    __table_args__ = (
        Index("idx_plugin_trust_plugin_project", "plugin_id", "project_id"),
        CheckConstraint(
            "consent_model in ('integrity_not_sandbox')",
            name="ck_plugin_trust_consent_model",
        ),
    )

    trust_record_id: Mapped[str] = mapped_column(String, primary_key=True)
    plugin_id: Mapped[str] = mapped_column(ForeignKey("plugin_registrations.plugin_id"), nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.project_id"))
    consent_model: Mapped[str] = mapped_column(String, nullable=False)
    trust_acknowledgment_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    granted_capabilities_json: Mapped[list] = mapped_column(JSON, nullable=False)
    consented_at: Mapped[str] = mapped_column(String, nullable=False)
    revoked_at: Mapped[str | None] = mapped_column(String)
