# Product Requirements Document

## Product Vision

Atlas is an offline-first, privacy-first FiveM server development platform that combines an IDE, local DevOps control plane, resource manager, incident debugger, automation builder, and extensible module host. It should make professional FiveM server development safer, faster, and more understandable without requiring cloud services or taking control away from developers.

## Goals

- Reduce the manual work required to create, configure, update, monitor, debug, and maintain FiveM RP servers.
- Provide a local project model for artifacts, txAdmin data, server data, resources, configs, databases, backups, automations, incidents, and Git history.
- Make every file-changing or process-changing operation transparent before execution.
- Keep all FiveM project data local by default.
- Provide Sentry-inspired Incident Intelligence without uploading FiveM logs, resources, player data, databases, or configuration.
- Establish a modular architecture that supports first-party modules and third-party plugins without modifying core code.
- Support a professional developer workflow: diffs, validation, undo, Git integration, terminals, logs, and audit history.

## Non-Goals

- Atlas is not a hosted game-server panel in the first phases.
- Atlas is not a replacement for txAdmin's live administration and moderation surface.
- Atlas will not require accounts, cloud sync, proprietary backends, mandatory telemetry, or mandatory AI services.
- Atlas will not automatically send FiveM project data to Sentry, AI providers, or any remote service.
- Atlas will not implement database schema or module APIs during Phase 1-3 planning.
- Atlas will not scaffold production source code until the architecture deliverables are complete.
- Atlas will not attempt full IDE language intelligence for every FiveM resource language in the first release.

## Guiding Principle Fit

| Principle | Product Requirement |
| --- | --- |
| Offline first | Core project management, setup, monitoring, incident capture, backups, automations, and exports work without a network after required artifacts/resources are locally available. |
| Privacy first | FiveM resources, logs, player data, databases, configs, and secrets never leave the machine automatically. AI workflows are manual Markdown exports. |
| Developer first | Operations show intent, affected paths, commands, diffs, validation results, and undo plans before execution. |
| Modular | Features are split into independently maintainable modules with stable domain contracts and plugin extension points. |

## User Personas

### Solo FiveM Developer

Builds and tests resources locally, frequently edits configs, pulls community resources, and needs quick restart/debug loops.

Needs:
- Fast local workspace setup.
- Resource dependency visibility.
- Git status and rollback.
- Local incident reports optimized for AI assistance.

### RP Community Technical Lead

Maintains a production RP server with staging and production environments, multiple contributors, scheduled restarts, backups, and frequent resource updates.

Needs:
- Environment profiles.
- Safe update workflows.
- Backup/restore confidence.
- Incident history with Git and artifact context.
- Audit trails for automated actions.

### Server Host Or Managed Services Operator

Supports multiple customer servers and needs repeatable setup, validation, backups, and troubleshooting without leaking customer data.

Needs:
- Multi-project management.
- Templates and repeatable automations.
- Exportable reports.
- Strong privacy boundaries.
- Optional future remote/node management.

### Plugin Developer

Extends Atlas with validators, resource providers, setup recipes, incident enrichers, automation actions, or UI views.

Needs:
- Stable plugin SDK.
- Clear permission model.
- Local test harness.
- Versioned extension points.
- Documentation and examples.

### New Server Owner

Wants to create an RP server but does not yet understand artifacts, txAdmin, databases, resource load order, or server.cfg.

Needs:
- Wizard-driven setup.
- Explanations before changes.
- Validation and common-failure guidance.
- Conservative defaults.

## Feature List

### Project Management

- Multiple local server projects.
- Project import and discovery.
- Environment profiles such as local, staging, and production.
- Project templates and setup recipes.
- Workspace trust state.
- Per-project settings, artifact pins, and resource inventory.

### Initial Server Setup

- Guided artifact selection with Recommended/Latest distinction.
- FXServer artifact download and update workflow.
- txAdmin first-run guidance and compatibility checks.
- `server.cfg` generation and validation.
- Dependency and database setup checklist.
- Preflight validation before first launch.

### Resource Manager

- Install, update, enable, disable, delete, and rollback resources.
- Dependency graph and startup order visualization.
- Git origin, branch, commit, and local modification detection per resource.
- Resource health status and compatibility notes.
- Safe update previews with backups and restore points.

### Git Integration

- Clone repositories.
- Display branch, status, changed files, and diffs.
- Pull/fetch with conflict warnings.
- Commit selected changes.
- Compare commits.
- Associate incidents and backups with Git commits.
- Avoid GitHub-specific assumptions in the core model.

### Configuration Editor

- GUI-assisted editing for common FiveM and txAdmin-adjacent settings.
- Monaco-powered text editing for advanced users.
- Live validation.
- Search.
- Diff viewer.
- Undo history and snapshots.
- Secret detection warnings.

### Backup System

- Manual and scheduled backups.
- Config, resource, database, artifact metadata, and full snapshot modes.
- Compression and retention policies.
- One-click restore with preview.
- Backup verification.
- Local export/import.

### Monitoring Dashboard

- CPU, memory, disk, network, process state, server FPS, players, database health, and resource health.
- Real-time console streaming.
- Historical local metrics.
- Alerts that can create local incidents.
- Clear distinction between Atlas app metrics and FiveM project metrics.

### Incident Intelligence

- Local incident capture for crashes, startup failures, resource errors, validation failures, and automation failures.
- Timestamp, severity, category, stack trace, recent logs, runtime info, loaded resources, Git commit, environment snapshot, startup order, relevant configuration, and related incidents.
- Deduplication and fingerprinting.
- Timeline and breadcrumbs.
- Compare incidents.
- Markdown export optimized for manual AI debugging.
- No AI API integration.

### Automation Engine

- Visual trigger/action workflows.
- Triggers: Git pull completed, server crash, resource changed, schedule elapsed, validation failed, backup completed, incident created.
- Actions: restart server, restart resource, run validation, create backup, export report, notify locally, run command with approval.
- Dry run and approval gates.
- Durable schedule metadata.
- Audit logs and undo plans.

### Plugin System

- Plugin manifest with contribution points and required capabilities.
- Extension points for commands, views, validators, setup recipes, resource providers, incident enrichers, automation triggers/actions, and exporters.
- Project trust and capability approval before execution.
- Plugin lifecycle events.
- Local plugin development mode.

### Atlas Application Telemetry

- Optional Sentry integration for Atlas application failures only.
- User-visible telemetry controls.
- SDK-side sanitization before upload.
- Never include FiveM resources, logs, configs, databases, player data, IPs, Discord tokens, webhook URLs, license keys, API keys, database credentials, Steam identifiers, or Rockstar identifiers.

## Roadmap

### Phase 1: Research And Competitive Analysis

- Document comparable tools and lessons.
- Identify platform-specific constraints.
- Establish privacy and offline boundaries.

### Phase 2: PRD

- Define product goals, personas, features, risks, milestones, and non-goals.
- Confirm phase boundaries before implementation.

### Phase 3: High-Level Architecture

- Define frontend, backend, module, data-flow, plugin, incident, automation, and telemetry architecture.
- Produce Mermaid diagrams.
- Record assumptions and deviations.

### Phase 4: Repository Structure

- Create source layout, naming conventions, coding standards, dependency strategy, config strategy, tests, and CI/CD strategy.
- No feature implementation beyond scaffolding.

### Phase 5: Database Schema Design

- Design SQLite schema for projects, resources, configs, backups, incidents, automations, plugins, telemetry preferences, and audit history.
- Define migrations and data-retention strategy.

### Phase 6: Module API Design

- Specify commands, queries, events, repositories, service interfaces, plugin extension contracts, and adapter boundaries.
- Validate module API ergonomics before implementation.

### Phase 7: Implementation Roadmap

- Prioritize by business value and technical dependency.
- Define vertical slices and release gates.

## Milestones

### M0: Architecture Foundation

Acceptance:
- Brief, competitive analysis, PRD, and architecture docs exist under `/docs`.
- Open questions and assumptions are explicit.
- No production code exists.

### M1: Local Project Shell

Acceptance:
- Tauri shell launches local frontend.
- Local backend lifecycle is established.
- SQLite connection and settings storage are proven.
- No FiveM project data leaves the machine.

### M2: Project Import And Validation

Acceptance:
- Atlas imports an existing FiveM project.
- Displays artifacts, txAdmin data, server data, resources, configs, and Git status.
- Runs read-only validation and produces an explainable report.

### M3: Safe Resource And Config Workflows

Acceptance:
- Resource enable/disable/update and config edits show diffs and undo plans.
- Snapshots are created before risky changes.
- Git status is integrated into all workflows.

### M4: Incident Intelligence MVP

Acceptance:
- Captures local incidents from logs, process exits, validation failures, and automation failures.
- Groups incidents by fingerprint.
- Exports AI-ready Markdown without remote AI calls.

### M5: Automation MVP

Acceptance:
- Visual schedules and event-triggered workflows run locally.
- Actions support dry run, approval, audit logs, and failure incidents.

### M6: Plugin SDK Preview

Acceptance:
- Plugins can contribute validators, commands, exporters, and automation actions through a manifest.
- Capabilities and project trust gate execution.

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| FiveM artifact and txAdmin behavior changes | Setup/update workflows break or become unsafe | Keep artifact handling behind adapters; record artifact metadata; prefer Recommended channel. |
| Privacy boundary mistakes | User trust loss and possible sensitive data exposure | Default-deny outbound data; SDK-side telemetry sanitizer; tests for sanitization; explicit export flows. |
| Tauri/Python sidecar lifecycle complexity | Startup, update, and crash behavior becomes brittle | Treat process orchestration as a first-class subsystem; health checks; clear failure incidents. |
| SQLite concurrency limits | Background automation and UI writes may conflict | Single-writer Unit of Work policy; short transactions; job ownership; later migration path if needed. |
| Plugin security | Third-party plugins can access sensitive local data | Capability manifests, project trust, audit logs, signing/trust metadata in later phases, minimal APIs. |
| Scope creep into full IDE | Product becomes too broad before core workflows work | Prioritize FiveM lifecycle and incident workflows over generic code intelligence. |
| Hidden automation | Users lose confidence or accidentally damage projects | Mandatory preview/diff/undo patterns for file and process changes. |
| Incident noise | Local incident list becomes unusable | Fingerprinting, severity, deduplication, ignore rules, and related incident grouping. |
| Windows-first FiveM assumptions | Cross-platform design may suffer | Model platform-specific adapters and document Windows as the primary early validation target. |

## Assumptions

- Atlas starts as a local desktop platform using Tauri, React, TypeScript, FastAPI, Python, SQLAlchemy, APScheduler, GitPython, Pydantic, and SQLite unless later research justifies a change.
- The local backend is acceptable as a sidecar or local service boundary managed by the Tauri shell.
- Users are comfortable manually copying Markdown reports to AI tools rather than connecting AI APIs.
- Early releases should optimize for Windows FiveM development while preserving adapter boundaries for Linux/macOS where feasible.
- txAdmin remains bundled with FXServer artifacts and should be integrated through documented files/processes/APIs instead of reimplemented.

## Open Questions

- What is the first supported operating system matrix: Windows only, Windows plus Linux, or all Tauri desktop targets?
- Should Atlas eventually support remote production nodes, or remain a local development platform with export/deploy workflows?
- What plugin runtime is acceptable: Python plugins, JavaScript/TypeScript plugins, WebAssembly, or a manifest-first model with limited executable hooks?
- Which FiveM frameworks should receive first-party templates first: QBCore, ESX, vRP, or a framework-neutral minimal server?
- How much txAdmin API integration is acceptable before Atlas becomes dependent on txAdmin internals?
- Should Atlas support database engines beyond SQLite for managed server data, or only connect to external DBs as project dependencies?

## Recommended Deviations From The Brief

- Treat Atlas as a platform that may eventually manage remote nodes, but keep the first implementation strictly local to preserve the offline-first principle.
- Avoid CQRS in the initial architecture except for read-heavy dashboards and incident queries where it produces a clear benefit.
- Avoid React Server Components in the Tauri desktop frontend unless a future framework choice makes them valuable; Atlas is primarily a local client application.
- Do not make Docker or Podman a required dependency for the core product, even though Pterodactyl and AMP show the value of isolation.
