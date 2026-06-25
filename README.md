# Atlas

Atlas is an offline-first, privacy-first FiveM server development platform. It combines an IDE-like desktop experience with local DevOps tooling for developing, deploying, maintaining, monitoring, and debugging FiveM RP servers—without requiring cloud accounts or uploading FiveM project data.

## Guiding Principles

- **Offline first** — core workflows run locally without proprietary backends.
- **Privacy first** — resources, logs, configs, databases, and player data never leave the machine automatically.
- **Developer first** — every action is transparent: preview, diff, execute, audit, undo.
- **Modular** — bounded contexts with hexagonal architecture and a plugin SDK.

## Documentation

| Phase | Location |
| --- | --- |
| Brief | [docs/atlas-brief.md](docs/atlas-brief.md) |
| Research | [docs/research/competitive-analysis.md](docs/research/competitive-analysis.md) |
| PRD | [docs/prd.md](docs/prd.md) |
| Architecture | [docs/architecture/](docs/architecture/) |
| Standards | [docs/standards/](docs/standards/) |

## Repository Structure

```
Atlas/
├── backend/                 # Local FastAPI backend (hexagonal)
│   ├── api/                 # Routers, schemas, streams
│   ├── application/         # Use-case orchestration per module
│   ├── domain/              # Models, policies, ports, events
│   │   └── shared_kernel/   # Cross-module primitives
│   ├── adapters/            # Port implementations (filesystem, git, fivem, …)
│   └── infrastructure/      # Event bus, scheduler, UoW, DI
├── frontend/                # React + TypeScript + Vite UI
│   └── src/
│       ├── app/
│       ├── features/        # Feature slices aligned to bounded contexts
│       ├── components/
│       ├── api/             # Typed local API client
│       └── plugin-ui/
├── src-tauri/               # Tauri shell (windowing, capabilities, backend lifecycle)
├── plugin-sdk/              # Plugin manifest and contribution-point contracts
└── docs/                    # Planning and standards documentation
```

Each significant directory contains a `README.md` describing its single responsibility and dependency rules.

## Bounded Context Modules

The same eleven module slugs appear under `backend/domain/` and `backend/application/`:

`project`, `setup`, `resources`, `git`, `config`, `backup`, `monitoring`, `incident`, `automation`, `plugin`, `telemetry`

Frontend feature slices live under `frontend/src/features/` with aligned names (UI folder `incidents` maps to backend `incident`).

## Technology Intent

Documented in [docs/standards/dependency-strategy.md](docs/standards/dependency-strategy.md). **This repository phase contains no dependency manifests or lockfiles.**

- Frontend: React, TypeScript, Tauri, Vite, TailwindCSS, Monaco, xterm.js
- Backend: Python 3.13, FastAPI, SQLAlchemy, APScheduler, GitPython, Pydantic
- Data: SQLite
- Testing: pytest, Playwright (future)
- CI: GitHub Actions (future)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Phase Status

| Phase | Status |
| --- | --- |
| 1 — Research | Complete |
| 2 — PRD | Complete |
| 3 — Architecture | Complete |
| 4 — Repository structure | Complete (this scaffold) |
| 5 — Database schema | Planned |
| 6 — Module APIs | Planned |
| 7 — Implementation roadmap | Planned |

## Open Questions

- **Transport**: Tauri IPC vs loopback HTTP between frontend and backend (see [docs/architecture/overview.md](docs/architecture/overview.md)).
- **Plugin runtime**: Python, JavaScript, WebAssembly, or manifest-only hooks (see [docs/architecture/plugin-system.md](docs/architecture/plugin-system.md)).
- **Telemetry default**: opt-in vs opt-out with sanitization (see [docs/standards/configuration-strategy.md](docs/standards/configuration-strategy.md)).

## Scaffold Deviations

- No top-level `shared/` package; shared kernel lives at `backend/domain/shared_kernel/`.
- No `tests/` directory in Phase 4; layout described in [docs/standards/testing-strategy.md](docs/standards/testing-strategy.md).
- No CQRS-specific folders; queries will live under `application/<module>/` when implemented.
- Frontend feature folder `incidents` uses plural UI naming while backend uses `incident` slug.

## License

To be determined.
