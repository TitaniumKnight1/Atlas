# ADR-0023: Plugin Capability and Trust Model (M9a)

## Status

Accepted (M9a)

## Context

M9 introduces third-party plugins — inverting the threat model from Atlas-controlled code (privacy) to **untrusted external code** (security). M9a must define manifests, capabilities, grants, and trust **before** any plugin executes.

## Threat model (honest)

M9a originally records the **authoritative permission ledger** without executing plugin code. M9b chose subprocess isolation + JSON IPC, so plugin code no longer shares Atlas's interpreter, memory, SQLite connection, or imports.

Subprocess isolation contains Atlas memory reads, direct Atlas internal calls, and importing around the ledger. It does **not** provide OS-level confinement: the child process can still access filesystem and network resources available to the current user unless a future OS sandbox is added.

The capability/trust record remains the **authoritative permission ledger** that M9b/M9c enforce at the subprocess IPC boundary.

## M9a / M9b / M9c split

| Slice | Responsibility |
| --- | --- |
| **M9a** | Manifest schema, strict validation, registry, capability enum, grants, trust/consent, global kill switch. **No code execution.** |
| **M9b** | Plugin host, loading, runtime isolation choice, capability enforcement at call sites. |
| **M9c** | Contribution-point wiring (commands, views, automation, etc.). |

## Capability model

Fixed enumerated capabilities map to sensitive Atlas surfaces (config secrets, incidents, destructive ops, filesystem, network, telemetry). Default-deny; grants are explicit, revocable, audited, and recorded per plugin (optionally per project).

`telemetry-submit` does not bypass the M2 sanitizer — M9b must route through the same boundary.

## Trust / consent

Granting capabilities requires:

- `consent_model: integrity_not_sandbox`
- Verbatim acknowledgment of `HONEST_TRUST_WARNING`
- `user_confirmed: true`

Trust records are persisted in `plugin_trust_records`.

## Registry scoping

| Table | Scope |
| --- | --- |
| `plugin_registrations` | App-global |
| `plugin_settings` | App-global (kill switch) |
| `plugin_capability_grants` | Per plugin; `project_id` NULL = global grant |
| `plugin_trust_records` | Per plugin; optional `project_id` |

## No execution in M9a

Manifest reading uses declarative JSON parsing (`json.loads`) only. M9a never imports, loads, or runs plugin modules.

## Consequences

- UI and docs must repeat the honest trust warning.
- Security reviewers should evaluate M9b isolation separately from M9a consent mechanics.
- Plugin registry data is local-only; never telemetry.
