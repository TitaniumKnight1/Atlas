# Configuration Strategy

Atlas manages two distinct configuration domains that must never be conflated: **Atlas application configuration** and **FiveM project configuration**.

## Configuration Domains

| Domain | Owner | Examples | Leaves machine automatically? |
| --- | --- | --- | --- |
| Atlas app config | Atlas | Telemetry opt-in, UI preferences, backend port, plugin approvals | Only Atlas telemetry (sanitized), never FiveM data |
| FiveM project config | User's server project | `server.cfg`, `txData`, resource configs, databases | Never, unless user manually exports |

## Atlas Application Configuration (Future)

Planned locations (not created in Phase 4):

- Per-user settings store (likely SQLite-backed via `backend/adapters/persistence/`).
- Optional user-level config file in the OS app data directory.
- Environment variables for development overrides only (e.g., `ATLAS_BACKEND_PORT`, `ATLAS_LOG_LEVEL`).

Principles:

- Sensible offline-first defaults; no cloud account required.
- Telemetry disabled or opt-in per product decision at implementation time.
- Secrets (API keys, tokens) stored outside plain-text config where possible.
- All settings changes auditable when they affect project safety.

## FiveM Project Configuration

Atlas reads and may modify FiveM project files only through backend adapters with:

- Dry-run previews.
- Diff display.
- Snapshot/backup before risky writes.
- Undo plans where feasible.

Relevant paths (project-specific, not Atlas-owned):

- FXServer artifacts (engine binaries).
- `txData/` (txAdmin data).
- `server-data/` or equivalent server root.
- `resources/` and `server.cfg`.
- External database connection settings referenced by resources.

Atlas stores **references and metadata** in SQLite, not copies of entire project trees, unless explicitly snapshotted for backup or incident context.

## Environment Profiles

Each Atlas project may define environment profiles (`local`, `staging`, `production`) containing:

- Artifact channel or pinned version (Recommended vs Latest).
- Resource load order overrides.
- Validation rule sets.
- Automation policies.
- Backup retention policies.

Profiles are Atlas metadata layered over the same physical project paths, not separate cloud environments.

## Pathway 2 Dev/Prod Separation (ADR-0027)

For team-repo local dev (Pathway 2), FiveM config separation uses FXServer's `exec` directive:

- **Tracked:** `server.cfg` — shared ensures and framework settings; secrets as placeholders; ends with `exec server.cfg.local`.
- **Gitignored:** `server.cfg.local` — license key, DB/API convars, endpoints, hostname, slot limits, and other machine-local overrides.

Atlas inbound flows extract production secrets into the overlay and normalize the base. Return-path safety relies on gitignore (structural) plus pre-commit secret scanning (defense-in-depth). See [ADR-0027](../architecture/decisions/0027-pathway2-dev-prod-config-separation.md).

## Secrets Handling

- Never log secrets in Atlas telemetry.
- Scan configs for secret patterns before display and export.
- Incident and Markdown exports must warn when sensitive values may be included.
- Sanitization rules for Sentry are defined in [docs/architecture/telemetry-and-privacy.md](../architecture/telemetry-and-privacy.md).

## Plugin Configuration

Plugins declare capabilities in manifests. Runtime configuration for plugins is separate from core Atlas settings and requires explicit user approval when capabilities change.

## Open Questions

- Whether Atlas app settings live only in SQLite or also in a human-editable YAML/TOML file.
- Default telemetry posture: disabled until opt-in vs enabled with aggressive sanitization.
- How to represent multi-machine project paths when users move repositories.
