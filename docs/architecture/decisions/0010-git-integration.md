# ADR-0010: Git Integration, Reversibility, And Remote URL Redaction

## Status

Accepted

## Context

M4b adds local Git operations via GitPython behind a domain port. Git remotes are an outbound network path; repository contents, diffs, and remote URLs (which may embed credentials) are local FiveM project data per the M2 privacy boundary.

## Decision

### Remote URL redaction

- Credential-bearing remote URLs (`https://user:token@host/...`) are redacted to `https://[REDACTED]@host/...` before persistence, API responses, audit details, and SSE payloads.
- Raw credential URLs never reach telemetry, shared logs, or SSE output.

### No implicit network

- Fetch, pull, and clone only run when explicitly invoked by the user against a configured remote URL.
- No auto-push, background sync, or implicit upload of repository contents.

### Per-operation reversibility (honest)

| Operation | Reversibility | Mechanism |
| --- | --- | --- |
| Clone | Reversible | Undo removes cloned directory (`RemoveClonedRepositoryCompensation`) |
| Fetch | Not reversible | Preview notes additive ref updates only |
| Pull (clean tree) | Reversible | Undo soft-resets to prior HEAD |
| Pull (dirty tree) | Not cleanly reversible | Preview warns; no undo plan |
| Create commit | Reversible | Undo soft-resets to parent commit |
| Checkout ref | Reversible | Undo checks out prior branch/ref |
| Create branch | Low risk | No delete-on-undo (branch remains) |
| Delete branch | Often irreversible | Preview warns; no undo plan |
| Status/diff/compare | Read-only | No command/undo |

### SSE progress

Long-running clone/fetch/pull operations publish `OperationProgress` on the `op-progress` topic through the M0b event bus → `StreamEventBridge` → SSE hub (ADR-0008). No parallel progress channel.

## Consequences

- M5 resource installs can consume git capability without duplicating GitPython wiring.
- M7 export paths must still treat git metadata as sensitive.
- Tests use local temp repositories only; no internet remotes in CI.
