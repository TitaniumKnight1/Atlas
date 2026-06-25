# CI/CD Strategy

Phase 4 documents the intended continuous integration and delivery approach only. **No `.github/workflows/` files are created in this phase.**

## Repository And Branch Policy

- **Default branch**: `main`
- **Feature branches**: short-lived branches from `main`, merged via pull request.
- **Protected `main`**: require passing CI checks and at least one review before merge (when CI exists).
- **Release branches**: optional `release/*` for stabilization before tagged releases.

## Intended Pipeline Stages

When GitHub Actions workflows are added:

### 1. Lint And Format

- Python: ruff (lint + format) or equivalent — tool choice deferred.
- TypeScript: eslint + prettier — config deferred to implementation phase.
- Rust (Tauri): `cargo fmt` and `cargo clippy` when `src-tauri` is implemented.
- Markdown: optional link checking for `docs/`.

### 2. Type Check

- Python: `mypy` or `pyright` on `backend/`.
- TypeScript: `tsc --noEmit` on `frontend/`.

### 3. Unit And Integration Tests

- `pytest` for backend domain, application, adapters, and API.
- Coverage reporting optional; prioritize boundary and privacy tests over percentage targets.

### 4. Frontend Build

- `vite build` for production bundle validation.
- No deployment of frontend alone; it ships inside the Tauri app.

### 5. E2E Tests

- Playwright against packaged or dev Tauri build for critical workflows.
- Run on `main` and release candidates; optional on PRs for speed.

### 6. Desktop Build

- Tauri build for Windows (primary), Linux and macOS when supported.
- Artifact upload to GitHub Releases on tagged versions.

## Workflow Triggers (Future)

| Event | Jobs |
| --- | --- |
| Pull request to `main` | lint, typecheck, unit, integration |
| Push to `main` | full suite including E2E (optional stagger) |
| Tag `v*` | release build and GitHub Release publish |

## Secrets In CI

- CI secrets are for **building and publishing Atlas only** (code signing, Sentry auth token for release crash reporting setup).
- Never use CI to access user FiveM project data.
- Test fixtures must be synthetic; no production server credentials in workflows.

## Release Artifacts

- Windows installer (primary).
- Portable archive optional.
- Release notes generated from changelog or PR titles.
- SBOM generation deferred until dependency manifests exist.

## Explicitly Deferred

- `.github/workflows/*.yml`
- Code signing certificates and notarization steps
- Auto-update channel configuration (Tauri updater)

## Open Questions

- Whether to use GitHub-hosted runners only or self-hosted runners for FXServer integration tests.
- Code signing requirements for Windows SmartScreen trust on first release.
- Release cadence: continuous from `main` vs scheduled releases.
