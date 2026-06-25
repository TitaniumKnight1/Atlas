# Dependency Strategy

Phase 4 documents the intended toolchain and approval process only. **No dependency manifests, lockfiles, or package installations exist in this phase.**

## Intended Toolchain

From [docs/atlas-brief.md](../atlas-brief.md) and architecture docs:

### Frontend

- React
- TypeScript
- Tauri
- Vite
- TailwindCSS
- Monaco Editor
- xterm.js

### Backend

- Python 3.13
- FastAPI
- SQLAlchemy
- APScheduler
- GitPython
- Pydantic

### Data And Testing

- SQLite (Atlas metadata)
- pytest (backend tests)
- Playwright (E2E tests)

### Packaging And CI

- GitHub Actions (described in [ci-cd-strategy.md](./ci-cd-strategy.md), not enacted yet)

## Management Approach (Future)

When dependencies are introduced in a later phase:

1. **Python**: manage with `pyproject.toml` and a lock strategy (e.g., `uv.lock` or pinned requirements) — decision deferred until Phase 4 repository scaffolding is complete and implementation begins.
2. **Node**: manage with `package.json` and a lockfile (`package-lock.json` or `pnpm-lock.yaml`) — package manager choice deferred.
3. **Rust (Tauri)**: manage via `src-tauri/Cargo.toml` and `Cargo.lock` when the shell is implemented.
4. **Plugins**: plugin SDK dependencies must be declared in plugin manifests and reviewed separately from core dependencies.

## Approval Rules

- No new dependency without documenting why existing tools are insufficient.
- Prefer standard library or already-approved stack items before adding libraries.
- Security-sensitive areas (telemetry, filesystem, process control, plugins) require explicit review.
- Dependencies that imply network access or telemetry require privacy review.
- Avoid overlapping libraries for the same concern (e.g., multiple HTTP clients, multiple schedulers).

## Explicitly Deferred

The following files are **not** created in Phase 4:

- `pyproject.toml` with dependency lists
- `package.json` with dependency lists
- `requirements.txt` / `requirements-dev.txt`
- `package-lock.json`, `pnpm-lock.yaml`, `uv.lock`, `Cargo.lock`
- Tool configs that imply installed dev tools (`ruff.toml`, `eslint.config.js`, `tsconfig.json`, `pytest.ini`, `tauri.conf.json`)

Describe these in standards docs first; add manifests only when implementation starts and dependencies are approved.

## Open Questions

- Python package manager: `uv`, `poetry`, or plain `pip` + `venv`?
- Node package manager: `npm`, `pnpm`, or `yarn`?
- Whether Monaco and xterm.js are bundled at frontend or loaded dynamically.
- Whether Sentry SDKs are added to frontend, backend, or both with separate sanitization paths.
