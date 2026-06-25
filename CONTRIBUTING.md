# Contributing to Atlas

Thank you for contributing to Atlas, an offline-first FiveM server development platform.

## Before You Start

1. Read [docs/atlas-brief.md](docs/atlas-brief.md) for mission and guiding principles.
2. Read [docs/prd.md](docs/prd.md) for product scope and roadmap.
3. Read [docs/architecture/overview.md](docs/architecture/overview.md) for system design.
4. Read the [docs/standards/](docs/standards/) guides before writing code.

## Guiding Principles

- **Offline first** — no required cloud services or accounts.
- **Privacy first** — FiveM project data never leaves the machine automatically.
- **Developer first** — show what will change, why, and how to undo it.
- **Modular** — respect bounded contexts and hexagonal layering.

## Repository Structure

Place code only in the directory that matches its responsibility. Each significant folder has a `README.md` explaining what belongs there. When in doubt, read the nearest README and the architecture docs.

Dependency direction:

```
frontend → backend/api schemas
backend/api → backend/application → backend/domain ← backend/adapters
plugin-sdk → documents contracts; runtime hooks into backend/application/plugin
```

## Standards

| Document | Purpose |
| --- | --- |
| [naming-conventions.md](docs/standards/naming-conventions.md) | Paths, modules, events, API, plugins |
| [coding-standards.md](docs/standards/coding-standards.md) | Layering, typing, security |
| [dependency-strategy.md](docs/standards/dependency-strategy.md) | Toolchain and dependency approval |
| [configuration-strategy.md](docs/standards/configuration-strategy.md) | Atlas vs FiveM configuration |
| [testing-strategy.md](docs/standards/testing-strategy.md) | Test layout and priorities |
| [ci-cd-strategy.md](docs/standards/ci-cd-strategy.md) | Pipeline stages (not yet implemented) |

## Dependencies

Do not add dependencies without approval. Phase 4 intentionally contains **no** `pyproject.toml`, `package.json`, lockfiles, or tool configs. Propose new dependencies in a pull request with justification against [dependency-strategy.md](docs/standards/dependency-strategy.md).

## Pull Requests

- Keep changes focused on one concern.
- Do not modify unrelated files.
- Ensure new code respects module boundaries.
- Add or update tests when implementation begins (see testing strategy).
- Document open questions or architectural deviations explicitly.

## Privacy And Telemetry

- Never send FiveM resources, logs, configs, databases, or player data to Sentry or any remote service.
- Atlas telemetry is application-only and must pass through the sanitization layer.
- Incident exports are manual; do not add AI API integrations.

## Questions

Open architecture questions are listed in architecture and standards docs. Raise new questions in issues or pull request descriptions rather than silently changing requirements.
