# plugin-sdk\contribution-points\commands

## M9c contract

`commands` is the representative PRODUCING contribution.

Required capability: `read-project-metadata`.

Invocation:

1. Atlas invokes the command through the M9b subprocess host using mode `contribution:commands:<identifier>`.
2. The plugin requests only the capabilities it needs over JSON IPC.
3. The host re-checks live M9a grants and audits each call.
4. The plugin returns a `contribution_result` containing local output for Atlas to display.

Commands do not receive direct Atlas service objects, DB handles, or raw filesystem adapters.

## See also

[docs/architecture/plugin-system.md](../docs/architecture/plugin-system.md)
