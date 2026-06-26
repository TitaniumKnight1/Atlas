# ADR-0017: M7a Incident Capture and Environment Snapshot Assembly

## Status

Accepted

## Context

Atlas M7 (Incident Intelligence) is split into three slices:

- **M7a** — capture + environment snapshot assembly (this ADR)
- **M7b** — fingerprinting, deduplication, grouping, related incidents
- **M7c** — Markdown export with sanitization (deliberate outbound path per ADR-0005)

Incidents are the most secret-dense local objects in the system: config holds license keys, logs may contain tokens/IPs/player data, and git remotes can embed credentials. M7a must capture faithfully while creating **no telemetry path** and **no export/outbound path**.

## Decision

### Crash trigger

M7a subscribes to M3b's post-commit `ServerCrashed` domain event on the in-process event bus. The trigger path is:

`LocalProcessSupervisor` unexpected exit → `SetupApplicationService.record_process_exit(expected=False)` → persist crashed run + tails → `ServerCrashed` → `IncidentApplicationService._on_server_crashed` → `capture_server_crash`.

Explicit `POST /api/v1/projects/{project_id}/incidents/capture/crash` exists for tests and manual replay; the primary production trigger is the crash subscriber.

### Snapshot source map (read-only via existing services)

| Snapshot section | Source module | Read path |
| --- | --- | --- |
| Runtime / process | M3b | `SetupApplicationService.get_process_status` |
| Loaded resources + dependency graph | M5a | `ResourceApplicationService.list_resources`, `get_dependency_graph` |
| Startup / ensure order | M5a | `ResourceApplicationService.get_safe_start_order` |
| Relevant configuration | M4a | `ConfigApplicationService.list_config_files`, `list_secret_findings` (metadata only) |
| Git commit / branch | M4b | `GitApplicationService.list_git_repositories`, `get_worktree_status` + `redact_remote_url` |
| Recent metrics | M6a/M6b | `MonitoringApplicationService.latest_metrics`, `MonitoringRetentionService.query_time_window` |
| Logs | M3b | Bounded stdout/stderr tails from process status / run record |

M7a does **not** re-implement any of the above capabilities.

### Log availability (STEP 0 discovery)

M3b stores **bounded in-memory tails only** (`deque(maxlen=200)` per stream), persisted to `setup_process_runs.stdout_tail_json` / `stderr_tail_json` at exit. **No durable log history** exists.

Snapshots record this honestly:

- `availability: bounded_tail_only`
- `durable_history_available: false`
- `max_lines_per_stream: 200`

M7a never fabricates log lines beyond what M3b buffered.

### Persistence (M7a subset)

Implemented via idempotent SQLAlchemy bootstrap:

- `incident_groups` (one group per capture; placeholder fingerprint `capture:{occurrence_id}` — not M7b dedup)
- `incident_occurrences`
- `incident_breadcrumbs`
- `incident_context_snapshots`
- `incident_stack_traces`

**Deferred (not M7a):** `incident_fingerprints`, `incident_related_groups`, `incident_stack_frames`, `incident_exports`, `incident_group_rules`, `incident_notes`.

### Capture semantics

Crash capture is an audited UoW write (domain event `IncidentCaptured` on the local bus) but **not** a reversible user mutation: no preview, dry-run, or undo ceremony.

### Privacy boundary

- Incident rows are local project data only (see `telemetry-and-privacy.md`).
- M7a creates no route from incident storage to telemetry or export.
- Git remotes are redacted in environment snapshots.
- Config secret **values** are never widened; only M4a finding metadata is included.
- Export + sanitization is explicitly M7c.

## Consequences

- Operators get a self-contained local crash record suitable for later M7c export.
- Grouping/dedup quality is limited until M7b fingerprinting ships.
- Log context in snapshots is capped at 200 lines per stream unless M3b gains durable logging later.
