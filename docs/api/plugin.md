# Plugin API Contract

Responsibility: plugin registration, manifest validation, capability grants, contribution registry, lifecycle, project trust enforcement, and plugin-host boundary.

## Commands

| Name | Inputs | Outputs | Errors | Behavior | PRD trace |
| --- | --- | --- | --- | --- | --- |
| `DiscoverPlugins` | source filters | plugin candidates | `ExternalAdapterFailed` | Global scan; no activation. | Plugin SDK |
| `ValidatePluginManifest` | plugin source/manifest | validation report, capability list | `ValidationFailed` | Read-only security check. | Plugin manifest |
| `RegisterPlugin` | manifest, source ref, `idempotency_key` | plugin registration id | `ValidationFailed`, `Conflict`, `PermissionDenied` | Audited install/register. | Plugin lifecycle |
| `SetPluginEnabledState` | plugin id, enabled/restricted/disabled | plugin summary | `NotFound`, `PermissionDenied` | Audited lifecycle change. | Plugin lifecycle |
| `GrantPluginCapability` | plugin id, optional `project_id`, capability, scope | grant id | `PermissionDenied`, `ValidationFailed`, `ProjectScopeViolation` | User-approved capability. | Capability approval |
| `RevokePluginCapability` | plugin id, optional `project_id`, capability | grant summary | `NotFound` | Audited revocation. | Privacy/security |
| `RegisterContributionPoint` | plugin id, contribution type, descriptor | contribution id | `PermissionDenied`, `ValidationFailed` | Internal after activation. | Extension points |
| `RecordPluginFailure` | plugin id, optional `project_id`, failure summary | incident request ref | `ValidationFailed` | Publishes failure event. | Plugin loading failures |

## Queries

| Name | Inputs | Outputs | Errors | PRD trace |
| --- | --- | --- | --- | --- |
| `ListPlugins` | global/project filters | plugin summaries | none | Plugin management |
| `GetPlugin` | plugin id | manifest, state, capabilities | `NotFound` | Plugin detail |
| `ListPluginCapabilities` | plugin id, optional `project_id` | grants and requested capabilities | `NotFound` | Capability approval |
| `ListContributionPoints` | type, optional `project_id` | registered contributions | none | Plugin SDK |
| `GetPluginTrustState` | plugin id, `project_id` | effective trust/capability state | `NotFound`, `ProjectScopeViolation` | Project trust |

## Published Events

| Event | Payload summary | Consumers |
| --- | --- | --- |
| `PluginDiscovered` | plugin source, manifest summary | Audit |
| `PluginRegistered` | plugin id, version | Audit, Telemetry |
| `PluginEnabledStateChanged` | plugin id, state | Automation, Monitoring, Audit |
| `PluginCapabilityGranted` | plugin id, `project_id`, capability | Automation, Monitoring, Config, Incident |
| `PluginCapabilityDenied` | plugin id, `project_id`, capability, reason | Project, Automation, Audit |
| `PluginContributionRegistered` | plugin id, contribution type | Owning contribution context |
| `PluginFailureRecorded` | plugin id, `project_id`, failure | Incident, Telemetry |

## Subscribed Events

| Source event | Reaction | Reason |
| --- | --- | --- |
| `WorkspaceTrustChanged` | Recompute plugin effective permissions | Project trust enforcement. |
| `ProjectArchived` | Disable project-scoped plugin actions | Avoid hidden automation. |
| `TelemetryRejected` | Prevent plugin from weakening telemetry boundary | Privacy protection. |
| `AutomationApprovalRequested` | Validate plugin action capabilities | Plugin actions require grants. |

## Required Domain Ports

| Port | Purpose | Project scoping | Adapter target |
| --- | --- | --- | --- |
| `PluginRepositoryPort` | Persist registrations, grants, contributions | Project-scoped grants require `project_id`; global registrations explicit | `persistence` |
| `PluginHostPort` | Load/activate/deactivate plugin runtime boundary | Requires approved plugin state and capability scope | `plugin` |
| `ManifestValidationPort` | Validate manifest structure and declared capabilities | Global or project-scoped manifest context | `plugin` |
| `ProjectTrustPort` | Resolve project trust decisions | Requires `project_id` for project-scoped capabilities | Project contract |
| `AuditPort` | Record plugin lifecycle and grants | Includes `project_id` when scoped | `persistence` |

## API Surface

| Intent | Structural request | Structural response |
| --- | --- | --- |
| `GET /api/v1/plugins` | filters | plugin summaries |
| `POST /api/v1/plugins/discover` | source filters | candidates |
| `POST /api/v1/plugins/validate-manifest` | manifest/source | validation report |
| `POST /api/v1/plugins` | manifest/source | registration id |
| `PATCH /api/v1/plugins/{plugin_id}/state` | desired state | plugin summary |
| `GET /api/v1/projects/{project_id}/plugins/{plugin_id}/capabilities` | ids | effective grants |
| `POST /api/v1/projects/{project_id}/plugins/{plugin_id}/capabilities` | grant/deny request | grant result |
| `GET /api/v1/plugin-contributions` | type/project filters | contributions |

## Open Questions

- Which runtime is first supported: Python, JavaScript, WebAssembly, external process, or manifest-only hooks.

## Deviations

None.
