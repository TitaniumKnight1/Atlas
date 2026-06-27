# Atlas Contribution Points (M9c)

All contribution points use the same template:

1. The manifest declares a contribution descriptor:

```json
{
  "contribution_point": "commands",
  "identifier": "com.example.command",
  "title": "Example Command"
}
```

2. Atlas registers the contribution only when the plugin is enabled and the mapped M9a capability is granted for the project.
3. Atlas invokes the contribution through the M9b subprocess host using `contribution:<point>:<identifier>`.
4. Any Atlas data or mutation the contribution needs is requested over JSON IPC and checked against the live capability ledger.
5. The plugin returns `contribution_result`; failures are contained and recorded locally.

## Capability map

| Contribution point | Required capability |
| --- | --- |
| `commands` | `read-project-metadata` |
| `views` | `render-ui` |
| `resource-providers` | `invoke-resource-lifecycle` |
| `setup-recipes` | `invoke-setup-process` |
| `config-validators` | `read-config` |
| `incident-enrichers` | `read-incidents` |
| `report-exporters` | `read-incidents` + M7c sanitized export path |
| `automation-triggers` | `contribute-automation` |
| `automation-actions` | `invoke-resource-lifecycle` |
| `monitoring-collectors` | `contribute-monitoring` |

M9c wires `config-validators`, `automation-actions`, and `commands` as representative read/mutate/produce coverage. `report-exporters` are intentionally deferred until they can route entirely through the M7c sanitized export path and the export-sanitizer independent-audit gate.
