# ADR-0018: M7b Incident Fingerprinting, Deduplication, and Grouping

## Status

Accepted

## Context

M7a captured crash occurrences with placeholder fingerprints (`capture:{occurrence_id}`) and one group per capture. M7b repurposes `incident_groups` to mean one group per distinct issue (Sentry-style), with many occurrences deduplicated under a stable fingerprint.

M3b provides exit codes and bounded log tails only — no durable stack traces. Fingerprinting must be stack-trace-independent.

## Decision

### Fingerprint signal set (v1: `atlas-crash-v1`)

| Signal | Source |
| --- | --- |
| `category` | crash |
| `severity` | fatal |
| `source_type` | process |
| `exit_code` | runtime snapshot |
| `exception_type` | stack trace record (usually null) |
| `normalized_message` | occurrence message with variables stripped |
| `log_signature` | SHA-256 of last 5 normalized stdout/stderr tail lines |
| `resource_hint` | extracted from log patterns or explicit hint |

Final fingerprint = SHA-256 of canonical JSON components. **Raw log lines and secrets are never stored as the group key.**

### Normalization (before hashing)

Strip or replace: ISO timestamps, UUIDs, absolute paths, PIDs, ports, IPv4, long hex hashes, long numeric IDs, exit-code literals in messages, credential URLs, and token/secret patterns (`<secret>`).

### Grouping / dedupe semantics

- `decide_grouping(fingerprint, existing_group)` → `MATCH_EXISTING` or `CREATE_NEW`.
- Identical fingerprint → append occurrence to existing group; update `first_seen_at`, `last_seen_at`, `occurrence_count`.
- Distinct fingerprint → new group.
- Events: `NewIncidentGroupCreated`, `OccurrenceDeduplicated`, `IncidentGrouped` (local bus only).

### M7a → M7b transition

**Approach: idempotent backfill on access + explicit migrate endpoint.**

1. Detect groups with `capture:` placeholder fingerprints.
2. Recompute fingerprint from each occurrence's stored snapshots.
3. Bucket occurrences by fingerprint.
4. For each bucket: move occurrences to canonical group (existing real group or oldest placeholder), update fingerprint, recompute aggregates, delete empty placeholder groups.
5. Second run is a no-op when no placeholders remain.

No occurrences are duplicated or deleted. Loss-free and single-writer-safe via M0b UoW.

### Related groups (conservative)

Auto-link with `same_root_cause` (confidence 0.6) only when groups share a non-null `resource_hint`, have **different** fingerprints, and same project. No time-window over-linking.

### Privacy

Fingerprints and `incident_fingerprints.components_json` contain normalized hashes and metadata only — never raw secrets. Grouping data stays local SQLite; no telemetry or export path (M7c).

## Consequences

- Recurring crashes collapse into one issue group with accurate counts.
- Without stack frames, grouping relies on exit code + normalized log signature; materially different failures with identical signatures may over-group (acceptable v1 trade-off).
- Algorithm version field supports future regrouping when signals improve.
