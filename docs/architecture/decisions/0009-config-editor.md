# ADR-0009: Configuration Editor Ownership And Secret-Scan Policy

## Status

Accepted

## Context

M3a setup generates an initial `server.cfg` during the wizard using `RestoreServerConfigCompensation` and the shared `LocalSetupFilesystem` read/write port. M4a generalizes config editing for `server.cfg` and related files with scan, validation, diff, secret-scan, and undo.

## Decision

- **M3a** owns first-time setup generation of baseline `server.cfg` during the setup wizard.
- **M4a** owns ongoing config inventory, preview/apply/revert editing, validation, secret-scan findings, and undo history for all config files.
- Both reuse the same filesystem snapshot/restore compensation pattern (`prior_content` captured before write, restore on undo) via `ConfigFilesystemPort` implemented by `LocalSetupFilesystem`. M4a does not introduce a parallel undo mechanism.

Validation rules for `server.cfg` follow current Cfx.re vanilla server documentation: required `sv_licenseKey`, `endpoint_add_tcp` / `endpoint_add_udp` shape, placeholder license warnings, and endpoint port consistency checks. Tests stub these rules locally without network access.

Secret-scan uses the same secret vocabulary as M2's `SECRET_RULES` (license keys, tokens, DB connection strings, webhooks). Findings store only `redacted_preview` and `secret_type` metadata — never raw secret values in telemetry, logs, or outbound paths. Config secrets remain local FiveM project data per `telemetry-and-privacy.md`.

## Consequences

- Setup wizard continues to work without calling M4a.
- Config editor consumers use M4a APIs for all post-setup edits.
- M7 export paths must still treat config as sensitive; M4a only warns/masks locally.
