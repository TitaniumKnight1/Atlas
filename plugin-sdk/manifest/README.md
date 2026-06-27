# Atlas Plugin Manifest (M9a)

Declarative JSON manifest — parsed with `json.loads` only. Atlas **never imports plugin code** to read a manifest.

## Required fields

| Field | Type | Description |
| --- | --- | --- |
| `manifest_version` | string | Must be `"1"` |
| `plugin_id` | string | Reverse-DNS id (e.g. `com.example.my-plugin`) |
| `name` | string | Display name |
| `version` | string | Semver string |
| `author` | string | Publisher name |
| `contribution_points` | string[] | Declared contribution points (wired in M9c) |
| `requested_capabilities` | string[] | Least-privilege capability requests |
| `contributions` | object[] | Optional concrete contribution descriptors for M9c registration |

## Contribution points

- `commands`, `views`, `resource-providers`, `setup-recipes`, `config-validators`
- `incident-enrichers`, `report-exporters`, `automation-triggers`, `automation-actions`, `monitoring-collectors`

## Capabilities

| Capability | Sensitive surface |
| --- | --- |
| `read-project-metadata` | Project records |
| `read-config` | Config files / secrets (M4a) |
| `read-incidents` | Incident data (M7) |
| `read-git-metadata` | Git metadata |
| `invoke-resource-lifecycle` | Destructive resource ops (M5c) |
| `invoke-backup-restore` | Backup/restore (M8c) |
| `invoke-setup-process` | Server process control (M3b) |
| `filesystem-read` | Project filesystem read |
| `filesystem-write` | Project filesystem write |
| `network` | Outbound network |
| `telemetry-submit` | Atlas telemetry (sanitizer enforced in M9b) |
| `contribute-automation` | Automation triggers/actions |
| `contribute-monitoring` | Monitoring collectors |
| `render-ui` | Plugin UI surfaces |

Nothing is granted by default. Users must explicitly grant requested capabilities after reading the honest trust warning.

## Contribution descriptors

M9c accepts descriptors like:

```json
{
  "contribution_point": "config-validators",
  "identifier": "com.example.config.check",
  "title": "Example Config Check"
}
```

Atlas registers a descriptor only when the contribution point is declared and its required capability is granted for the project.

## Validation rules

- Unknown capabilities are **rejected** (not silently narrowed).
- Wildcard (`*`, `all`) requests are **rejected**.
- Requesting every capability is **rejected** as over-broad.
- Each requested capability must be justified by a declared contribution point.

## Trust model (honest)

Atlas runs plugins in a subprocess and mediates Atlas access over JSON IPC. This contains Atlas memory/DB/ledger bypass, but it is not OS-level confinement: the plugin subprocess still has the filesystem/network access allowed to the current user unless future OS sandboxing is added. See ADR-0023/0024.

## Example

See [example.manifest.json](./example.manifest.json).
