from __future__ import annotations

from enum import StrEnum


class PluginCapability(StrEnum):
    READ_PROJECT_METADATA = "read-project-metadata"
    READ_CONFIG = "read-config"
    READ_INCIDENTS = "read-incidents"
    READ_GIT_METADATA = "read-git-metadata"
    INVOKE_RESOURCE_LIFECYCLE = "invoke-resource-lifecycle"
    INVOKE_BACKUP_RESTORE = "invoke-backup-restore"
    INVOKE_SETUP_PROCESS = "invoke-setup-process"
    FILESYSTEM_READ = "filesystem-read"
    FILESYSTEM_WRITE = "filesystem-write"
    NETWORK = "network"
    TELEMETRY_SUBMIT = "telemetry-submit"
    CONTRIBUTE_AUTOMATION = "contribute-automation"
    CONTRIBUTE_MONITORING = "contribute-monitoring"
    RENDER_UI = "render-ui"


ALL_PLUGIN_CAPABILITIES = frozenset(PluginCapability)


RESTRICTED_CAPABILITIES = frozenset(
    {
        PluginCapability.READ_CONFIG,
        PluginCapability.READ_INCIDENTS,
        PluginCapability.INVOKE_RESOURCE_LIFECYCLE,
        PluginCapability.INVOKE_BACKUP_RESTORE,
        PluginCapability.INVOKE_SETUP_PROCESS,
        PluginCapability.FILESYSTEM_WRITE,
        PluginCapability.NETWORK,
        PluginCapability.TELEMETRY_SUBMIT,
    }
)


class ContributionPoint(StrEnum):
    COMMANDS = "commands"
    VIEWS = "views"
    RESOURCE_PROVIDERS = "resource-providers"
    SETUP_RECIPES = "setup-recipes"
    CONFIG_VALIDATORS = "config-validators"
    INCIDENT_ENRICHERS = "incident-enrichers"
    REPORT_EXPORTERS = "report-exporters"
    AUTOMATION_TRIGGERS = "automation-triggers"
    AUTOMATION_ACTIONS = "automation-actions"
    MONITORING_COLLECTORS = "monitoring-collectors"


CONTRIBUTION_CAPABILITY_ALLOWLIST: dict[str, frozenset[PluginCapability]] = {
    ContributionPoint.COMMANDS.value: frozenset(
        {PluginCapability.READ_PROJECT_METADATA, PluginCapability.FILESYSTEM_READ, PluginCapability.FILESYSTEM_WRITE}
    ),
    ContributionPoint.VIEWS.value: frozenset({PluginCapability.RENDER_UI, PluginCapability.READ_PROJECT_METADATA}),
    ContributionPoint.RESOURCE_PROVIDERS.value: frozenset(
        {PluginCapability.FILESYSTEM_READ, PluginCapability.INVOKE_RESOURCE_LIFECYCLE}
    ),
    ContributionPoint.SETUP_RECIPES.value: frozenset(
        {PluginCapability.READ_PROJECT_METADATA, PluginCapability.INVOKE_SETUP_PROCESS}
    ),
    ContributionPoint.CONFIG_VALIDATORS.value: frozenset({PluginCapability.READ_CONFIG}),
    ContributionPoint.INCIDENT_ENRICHERS.value: frozenset({PluginCapability.READ_INCIDENTS}),
    ContributionPoint.REPORT_EXPORTERS.value: frozenset({PluginCapability.READ_INCIDENTS}),
    ContributionPoint.AUTOMATION_TRIGGERS.value: frozenset({PluginCapability.CONTRIBUTE_AUTOMATION}),
    ContributionPoint.AUTOMATION_ACTIONS.value: frozenset(
        {PluginCapability.CONTRIBUTE_AUTOMATION, PluginCapability.INVOKE_RESOURCE_LIFECYCLE}
    ),
    ContributionPoint.MONITORING_COLLECTORS.value: frozenset({PluginCapability.CONTRIBUTE_MONITORING}),
}


class PluginRegistrationStatus(StrEnum):
    REGISTERED = "registered"
    DISABLED = "disabled"
    RESTRICTED = "restricted"


class PluginTrustStatus(StrEnum):
    PENDING_CONSENT = "pending_consent"
    CONSENTED = "consented"
    DENIED = "denied"
    REVOKED = "revoked"


class ConsentModel(StrEnum):
    INTEGRITY_NOT_SANDBOX = "integrity_not_sandbox"


HONEST_TRUST_WARNING = (
    "Atlas plugins run in-process with the backend. Python provides no real security sandbox: "
    "a malicious plugin can bypass capability checks using the shared interpreter. "
    "Capability grants are an integrity and informed-consent mechanism for trusted plugins, "
    "not isolation against a determined attacker. Only install plugins you trust."
)


class PluginSettingKey(StrEnum):
    GLOBAL_ENABLED = "global_enabled"
