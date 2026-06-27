# plugin-sdk\contribution-points\config-validators

## M9c contract

`config-validators` is the representative READ contribution.

Required capability: `read-config`.

Invocation:

1. Atlas invokes the contribution through the M9b subprocess host using mode `contribution:config-validators:<identifier>`.
2. The plugin requests `read-config` over JSON IPC.
3. The host re-checks the live M9a grant and returns config metadata only if granted.
4. The plugin emits a `contribution_result` with validation findings.

Example result:

```json
{
  "findings": [
    {"severity": "info", "message": "config files visible: 1"}
  ]
}
```

No validator receives config data without the `read-config` grant.

## See also

[docs/architecture/plugin-system.md](../docs/architecture/plugin-system.md)
