# ADR-0025: Plugin Contributions (M9c)

## Status

Accepted (M9c)

## Context

M9a records plugin manifests, trust, and capability grants. M9b runs plugin code in an isolated subprocess and enforces grants at the JSON IPC boundary. M9c lets plugins extend Atlas through contribution points without creating a side door around M9b enforcement.

## Decision

All contribution invocation crosses the M9b subprocess host. Atlas never imports contribution code into the backend interpreter. Contribution data access and mutations are structured uses of M9b capability mediation.

## Contribution to capability map

| Contribution point | Required capability |
| --- | --- |
| `commands` | `read-project-metadata` |
| `views` | `render-ui` |
| `resource-providers` | `invoke-resource-lifecycle` |
| `setup-recipes` | `invoke-setup-process` |
| `config-validators` | `read-config` |
| `incident-enrichers` | `read-incidents` |
| `report-exporters` | `read-incidents` plus the M7c sanitized export path |
| `automation-triggers` | `contribute-automation` |
| `automation-actions` | `invoke-resource-lifecycle` |
| `monitoring-collectors` | `contribute-monitoring` |

Default-deny applies. A contribution descriptor is registered only when the plugin is enabled, the contribution point is declared, and the required capability is granted for the project. Revoking the capability, disabling the plugin, or using the global plugin kill switch disables the contribution live.

## Representative wired set

M9c wires three contribution points:

- `config-validators` — READ contribution. Plugin requests `read-config`, receives gated config metadata, and returns findings.
- `automation-actions` — MUTATING contribution. Plugin requests `invoke-resource-lifecycle`; Atlas performs the mutation through M1 command audit with undo compensation.
- `commands` — PRODUCING contribution. Plugin requests `read-project-metadata` and returns local output.

The remaining contribution points follow the same descriptor -> capability check -> subprocess invocation -> audited IPC mediation template.

## Export safety

`report-exporters` are not wired in M9c. A report exporter must route through the M7c sanitized incident export path and is now validated by ADR-0005/0019's independent adversarial audit gate. Plugins cannot create a separate unsanitized incident export path.

## Consequences

Plugin contributions are transparent and enumerable in `plugin_contributions`. Contribution failures remain contained by M9b subprocess isolation and are local-only. This completes M9 and the roadmap's plugin-system proof without adding new dependencies or frontend work.
