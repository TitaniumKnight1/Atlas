# plugin-sdk\contribution-points\automation-actions

## M9c contract

`automation-actions` is the representative MUTATING contribution.

Required capability: `invoke-resource-lifecycle`.

Invocation:

1. Atlas invokes the contribution through the M9b subprocess host using mode `contribution:automation-actions:<identifier>`.
2. The plugin requests a mediated mutation over JSON IPC.
3. The host re-checks the live M9a grant.
4. The host performs the mutation through Atlas services and M1 `CommandAuditRecorder`, including undo compensation.
5. The plugin receives only the command result, not raw adapter access.

Destructive automation actions must be paired with M8b approval tiering when exposed as real automation recipes. M9c proves the subprocess/mediation pattern; rich recipe wiring remains a future extension.

## See also

[docs/architecture/plugin-system.md](../docs/architecture/plugin-system.md)
