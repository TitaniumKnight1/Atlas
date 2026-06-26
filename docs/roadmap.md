# Atlas Implementation Roadmap (Phase 7)

Ordered by two rules in tension: build the riskiest assumptions and the most-depended-on foundations first, and do not build a module before the things that give it value exist. Everything is project_id-scoped, so Project is the root. The flagship features (Incident Intelligence, Automation) consume other modules' context and operations, so despite being headline value they land late — built early they would ship empty. The largest risk is whether a Python backend packages and runs reliably inside Tauri; that is proven before anything else.

## Milestones

### M0 — Risky foundation + walking skeleton
Tauri launches, starts the embedded FastAPI backend, frontend calls one real endpoint, clean shutdown. Stand up persistence (engine, WAL, single-writer Unit of Work), the shared_kernel primitives, the in-process event bus, the DI container, app shell + typed API client. Resolves the two open gating decisions: frontend-backend transport (IPC vs loopback HTTP) and the Python-in-Tauri sidecar lifecycle. Highest risk in the project — sidecar packaging, port handshake, and shutdown races can invalidate architecture assumptions, so they are proven first. Exit: the bundled app round-trips a health check and CI builds it.

### M1 — Project context
Create/open/list projects, environment profiles, settings, paths. First full vertical slice through every layer; becomes the template for all later modules. The command infrastructure with developer-first transparency (preview / dry-run / undo / audit) is built here because every later command inherits it. Lowest-risk real module. Exit: projects persist across restarts and the audit log records operations.

### M2 — Telemetry sanitizer + crash capture (thin)
Opt-in/disable preference, the sanitization layer (strip license keys, tokens, IPs, DB credentials, Steam/Rockstar IDs, player info), local queue, Atlas-only Sentry wiring. Placed early on purpose: capture your own dev crashes from the start, and the sanitizer is leak-critical, so it is in place and tested before sensitive data flows everywhere. Risk: PII leak if incomplete — treat as security-grade.

Precondition before any future Sentry SDK/transport milestone: the ADR-0005 independent adversarial sanitizer audit gate must pass, and telemetry remains disabled by default until then.

### M3 — Setup & Artifacts + process supervision
The onboarding wizard (download artifacts, configure txAdmin, generate server.cfg, install dependencies, create database, validate) plus the process adapter to start/stop/supervise the server. First big user-facing payoff — you can stand up a running server — and it unblocks everything needing one (monitoring, incidents, automation). Risk: MEDIUM-HIGH — artifact channels, txAdmin handoff, heavy filesystem mutation (leans on dry-run/undo from M1).

### M4 — Config editor + Git integration (paired)
Config (scan/snapshot/changeset/validate/diff/undo, Monaco) and Git (clone/fetch/pull/branches/status/diff/commit via GitPython). Paired because they complete the "edit and version your server" story, and Git must exist before Resources (repo-based installs). Both filesystem-centric, moderate risk.

### M5 — Resource Manager (flagship #1)
Inventory, install/update/enable/disable/delete/rollback, dependency graph, version management, health, provenance. Depends on project + filesystem + git + config — its whole dependency set is now satisfied. The daily-driver module. Risk: MEDIUM-HIGH — dependency-graph correctness, rollback safety, startup-order interactions.

### M6 — Monitoring
Metric sources, samples, rollups/downsampling, alerts, health, live streams (CPU/mem/disk/FPS/players/network/DB). Needs a running server (M3) and feeds Incident Intelligence next. Exercises the time-series retention the schema designed. Risk: MEDIUM — sample volume, stream backpressure.

### M7 — Incident Intelligence (flagship #2)
Fingerprinting, deduplication, grouping, timeline/breadcrumbs, the full environment snapshot (loaded resources, git commit, config, startup order, recent logs, runtime), related incidents, AI-ready Markdown export. Placed here, not earlier, precisely because it is the flagship — its value is snapshot richness, which pulls from project, process, config, git, resources, and monitoring. Built before those, it would ship empty reports. Must consume via events/ports, never reaching into other domains. Exit: a real crash yields a grouped incident with a complete snapshot and clean Markdown export.

### M8 — Automation Engine + Backup (paired)
Automation (workflows, triggers, conditions, actions, APScheduler schedules, runs, approvals, idempotency) and Backup (plans, scheduled backups, restore, retention, compression). Both orchestrate and safeguard earlier modules' operations — they can only automate capabilities that already exist. Paired because they share scheduler ownership, stress-tested here against the single-writer model. Risk: MEDIUM — scheduler duplicate-job/ownership, destructive automations (approvals/dry-run critical).

### M9 — Plugin Platform
Manifest validation, registration, capabilities/trust, contribution-point wiring, lifecycle, plugin-ui host. Last because contribution points expose seams from every prior module and must be stable before committing to an SDK contract. Gate before starting: resolve the open plugin-runtime decision (Python/JS/WASM). Risk: MEDIUM-HIGH — sandboxing, capability enforcement, API-stability commitment.

## Threaded throughout (not milestones)
Developer-first transparency (from M1), the project_id isolation invariant (from M1, every scoped operation), testing per layer + Playwright E2E (from M0), and the CI bundle build (from M0).
