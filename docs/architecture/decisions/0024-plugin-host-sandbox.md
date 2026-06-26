# ADR-0024: Plugin Host and Subprocess Sandbox (M9b)

## Status

Accepted (M9b)

## Context

M9a defined the capability ledger and trust/consent model but executed no plugin code. M9b must load untrusted plugins and **enforce** grants at runtime.

## Decision: subprocess isolation + JSON IPC (stdlib)

Plugins run in a **separate Python process** launched via `subprocess` with newline-delimited JSON on stdin/stdout. The plugin process does not share Atlas's interpreter, memory, SQLite connections, or imports.

Bootstrap: `plugin-sdk/ipc/bootstrap.py` (stdlib only — never imports Atlas backend).

## Capability mediation

Plugins send `capability_request` messages. The Atlas host:

1. Re-reads M9a grants from `plugin_capability_grants` (default-deny).
2. Honors `plugin_settings.global_enabled` and per-plugin `is_enabled`.
3. If granted, performs the action via existing Atlas services (mutations via M1 command audit + undo).
4. If denied, returns an IPC error and audits the denial.
5. Records every attempt in `plugin_capability_calls`.

## Honest security posture

**What subprocess isolation contains:**

- Reading Atlas process memory
- Importing around the capability ledger
- Direct calls into Atlas internals / DB

**What it does NOT contain (out of scope for M9b):**

- OS-level confinement of filesystem/network available to the user running Atlas
- A malicious plugin can still touch paths and network the OS permits unless further sandboxing is added later

Capability grants are **enforced at the IPC boundary**, not cooperative in-process checks.

## Failure isolation

- Startup timeout: 5s
- Per-call IPC wait: configurable (10s default; tests use shorter hang kill at 3s)
- Plugin crash/hang does not crash Atlas
- Teardown reuses M3b process-tree discipline (`taskkill /T` on Windows, process group kill on POSIX)
- Failures recorded locally in `plugin_runtimes.failure_summary_json` — sanitized, never raw telemetry

## M9b tables

| Table | Scope |
| --- | --- |
| `plugin_runtimes` | Per plugin + project subprocess session |
| `plugin_capability_calls` | Per-call mediation audit |

M9c wires contribution points; M9b does not.

## Consequences

- M9a `HONEST_TRUST_WARNING` (in-process) is superseded at runtime by subprocess + mediation, but OS-privilege limits must still be disclosed in UI/docs.
- `telemetry-submit` and `network` capabilities are denied or stub-blocked at the host until explicitly designed with sanitizer routing.
