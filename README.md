<div align="center">

# Atlas

**A local-first, offline-first platform for FiveM server development.**

Your server. Your data. Your machine. Nothing leaves unless you send it.

[Features](#features) · [Architecture](#architecture) · [Getting Started](#getting-started) · [Philosophy](#design-philosophy)

<!-- Add a hero screenshot here (e.g. monitoring dashboard or resource manager). design/atlas-design-system.html is a static reference only — no bundled app screenshot yet. -->

</div>

---

## What is Atlas?

Atlas is a desktop application for building, running, and operating FiveM servers — artifact setup, resource management, configuration, git integration, live monitoring, crash intelligence, automation, backups, and a plugin system — in one place, running entirely on your own machine.

It is built on three commitments that shape every feature:

- **Local-first.** Your server config, secrets, logs, metrics, and backups live on your machine and are never transmitted anywhere. There is no cloud, no account, and no telemetry pipeline that ships your project data off-box. Optional Atlas error reporting is off by default, requires explicit consent, and passes through a fail-closed sanitizer when enabled.
- **Reversible.** Every operation that changes your server — installing a resource, editing config, restoring a backup — can be previewed before it runs and undone after. Atlas shows you exactly what it will do, then lets you take it back.
- **Honest.** Atlas tells you the truth about its own limitations. When a metric isn't reachable, it says "not available" instead of faking a number. When the plugin sandbox can't contain malicious code, it says so plainly instead of claiming a security guarantee it can't keep.

---

## Features

**Projects** — Import, open, and list local server workspaces with environment profiles, settings, paths, and trust decisions.

**Server setup & supervision** — A guided wizard for downloading FXServer artifacts, configuring `server.cfg`, and validating dependencies. Start, stop, and restart your server with live console output (SSE) and crash detection.

**Resource management** — Inventory your resources with a dependency graph, install and update with safety checks, and roll back changes with dependency-ordered, stop-and-hold compensation when something fails.

**Configuration editor** — Edit `server.cfg` and related files with diff previews before you save, validation findings, and a secret scanner that flags exposed keys (always masked, never revealed).

**Git integration** — Clone, fetch, pull, branch, commit, and compare — with remote URLs always redacted so credentials never end up in logs or snapshots.

**Live monitoring** — A real-time dashboard for host CPU and memory, supervised-process metrics, disk usage for the project root, live FiveM player count (from `dynamic.json`), resource health samples, historical charts, and alerting. Server FPS, network throughput, and database health are intentionally deferred and surface as **not available** rather than fabricated values.

**Incident intelligence** — Automatic crash capture with full environment snapshots, fingerprint-based deduplication that groups recurring crashes, and an AI-ready Markdown export — sanitized by an independently-audited redaction pass — that you can paste into the assistant of your choice.

**Automation** — Event- and schedule-driven recipes (restart-on-crash, post-pull validation, nightly maintenance) with a safety model that requires human approval before any destructive action runs.

**Backup & restore** — Consistent point-in-time backups with compression and retention policies, and a restore path that snapshots your current state first so the restore itself can be undone.

**Plugin system** — Extend Atlas with third-party plugins that run in an isolated subprocess, declare the capabilities they need, and require your explicit consent before accessing anything.

---

## Architecture

Atlas is a Tauri desktop application: a Rust shell hosting a React/TypeScript frontend, with a Python backend running as a PyInstaller-built sidecar process. The frontend and backend communicate over loopback HTTP and multiplexed SSE — everything stays on `127.0.0.1`.

```
┌─────────────────────────────────────────┐
│  Tauri Shell (Rust)                      │
│  ┌────────────────────────────────────┐  │
│  │  Frontend (React + TypeScript)     │  │
│  └────────────────┬───────────────────┘  │
│                   │ loopback HTTP + SSE   │
│  ┌────────────────┴───────────────────┐  │
│  │  Backend Sidecar (Python/FastAPI)  │  │
│  │  · single-writer SQLite (WAL)      │  │
│  │  · command/undo contract           │  │
│  │  · synchronous event bus           │  │
│  └────────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

A few load-bearing decisions:

- **Single-writer model** — All database writes go through one process-local lock and a Unit-of-Work pattern, so no background job, scheduler, or plugin can ever cause a concurrent-write conflict.
- **Command/undo contract** — Every mutating operation follows the same shape: preview → dry-run → execute → undo, with reversal handled by compensating actions rather than fragile rollbacks.
- **Privacy boundary** — Config secrets, incident snapshots, server logs, git remotes, metrics, and backups are local-only by construction. Git remotes are redacted before storage; the one deliberate outbound artifact you choose — the incident export — passes through an independently-audited sanitizer.

The full decision record lives in [`docs/architecture/decisions`](docs/architecture/decisions) (**24** ADRs). Highlights:

| ADR | Title |
| --- | --- |
| [0001](docs/architecture/decisions/0001-frontend-backend-transport.md) | Frontend-Backend Transport (loopback HTTP) |
| [0002](docs/architecture/decisions/0002-m0b-uow-event-dispatch.md) | M0b Unit Of Work And Event Dispatch Semantics |
| [0003](docs/architecture/decisions/0003-command-undo-contract.md) | Command Preview, Dry Run, Audit, And Undo Contract |
| [0005](docs/architecture/decisions/0005-telemetry-sanitizer.md) | Telemetry Sanitizer Boundary |
| [0019](docs/architecture/decisions/0019-incident-export.md) | M7c Incident Markdown Export and Export Sanitizer |
| [0024](docs/architecture/decisions/0024-plugin-host-sandbox.md) | Plugin Host and Subprocess Sandbox (M9b) |

---

## Getting Started

> [!IMPORTANT]
> Commands below are taken from the repository manifests (`package.json`, `src-tauri/tauri.conf.json`, `backend/requirements-dev.txt`, and [`.github/workflows/ci.yml`](.github/workflows/ci.yml)). Verify locally on your machine before relying on them in production.

**Prerequisites**

- **Rust** — stable toolchain (`rustup toolchain install stable` in CI; no `rust-toolchain.toml` in the repo)
- **Node.js** — **22** (used in CI; `frontend/package.json` has no `engines` field)
- **Python** — **3.13** (used in CI; documented in [`docs/standards/dependency-strategy.md`](docs/standards/dependency-strategy.md); not pinned in `requirements.txt`)

**Install dependencies** (from the repository root)

```bash
python -m pip install --upgrade pip
python -m pip install -r backend/requirements-dev.txt
npm install
npm install --prefix frontend
```

**Run in development**

```bash
python scripts/generate_tauri_icons.py   # required before the first Tauri build (CI runs this)
npm run tauri:dev
```

`npm run tauri:dev` builds the Python sidecar with PyInstaller (`scripts/build_backend_sidecar.py`) and starts `tauri dev`, which serves the frontend at `http://127.0.0.1:1420` per `src-tauri/tauri.conf.json`.

**Run backend tests**

```bash
npm run backend:test
```

(`python -m pytest` — see root `package.json`.)

**Build (production desktop bundle)**

```bash
npm run tauri:build
```

This runs `tauri build`. The `beforeBuildCommand` in `tauri.conf.json` builds the frontend (`npm run build` in `frontend/`) and rebuilds the PyInstaller sidecar, then bundles it as `binaries/atlas-backend` for Windows NSIS (`targets: "nsis"`). CI currently builds and smoke-tests on **windows-latest**.

---

## Design Philosophy

Atlas was built foundation-first: each capability was proven in isolation before the next was layered on, and every milestone audited its own assumptions against the project's privacy and safety boundaries before shipping. The result is a tool that's honest about what it does and what it can't.

Three principles, concretely:

**It never hides what it's doing.** Automations are visible and approval-gated. Destructive actions show a preview. The audit log records what every operation — and every plugin — actually did.

**It never claims safety it can't deliver.** The plugin system uses real subprocess isolation, but it tells you plainly that this contains plugins from Atlas's own memory, not from your operating system. The incident export is sanitized, but that sanitizer was independently attacked before the gate was closed — and the codebase says so.

**It keeps your data yours.** There is no telemetry path for your local project data. The single outbound feature you can use — exporting a crash report to debug with an AI — sanitizes secrets first and shows you what it redacted before you copy it.

---

## Status

- **Tests:** **250** pytest tests passing on `main` (integration + unit; run `npm run backend:test` to verify locally).
- **Roadmap:** Backend milestones **M0–M9** are implemented (walking skeleton through plugin contributions). The React feature shell covers all nine slices — Projects, Setup, Resources, Git, Config, Monitoring, Incidents, Automation, Backup, and Plugins — each marked `implemented: true` in `frontend/src/app/routes.ts`.
- **Release:** Version **0.0.0** — local-first desktop software under active development; **not yet publicly released** as a distributable product.
- **Follow-up:** Automation and monitoring retention each own an in-process scheduler thread (ADR-0020); consolidating scheduler ownership is a known deferred polish item, not a functional blocker.

## License

License not yet specified — no `LICENSE` file is present in the repository root.
