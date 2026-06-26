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
