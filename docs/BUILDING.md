# Building Atlas

## Maintainer release builds (Sentry error reporting)

Atlas can optionally report **Atlas application errors only** (crashes and bugs in Atlas itself) to the maintainer's Sentry project. This is **opt-in for end users** and scrubbed by the audited telemetry sanitizer. User FiveM project data is never sent.

### Build-time DSN injection

The maintainer's Sentry DSN is **never committed to source**. It is injected at **build time** from the build environment.

**Recommended (local release builds):** copy `.env.release.example` to `.env.release` (gitignored), set your real DSN there, then build. `scripts/build_backend_sidecar.py` loads `.env.release` automatically when `ATLAS_SENTRY_DSN` is not already set in the shell.

```bash
cp .env.release.example .env.release   # Windows: copy .env.release.example .env.release
# Edit .env.release — set ATLAS_SENTRY_DSN to your Sentry project DSN
python scripts/build_backend_sidecar.py
```

**CI / shell export** (same variable, no file):

```bash
export ATLAS_SENTRY_DSN="https://<public-key>@<org>.ingest.sentry.io/<project-id>"
python scripts/build_backend_sidecar.py
```

Precedence for the build: existing shell/CI `ATLAS_SENTRY_DSN` wins over `.env.release`.

`scripts/build_backend_sidecar.py` writes `backend/infrastructure/build_config_generated.py` (gitignored) with the DSN constant, then runs PyInstaller. That generated module is bundled into the distributed sidecar binary.

If `ATLAS_SENTRY_DSN` is **absent** during the build (e.g. a contributor building from source), the build **succeeds** with an empty baked DSN — that artifact reports nowhere.

### Runtime DSN precedence

1. **Build-time baked DSN** (present in distributed binaries from maintainer builds)
2. **`ATLAS_SENTRY_DSN` environment variable** (development override when no baked DSN)
3. **None** → telemetry delivery stays on the local no-op transport

End-user consent (`telemetry_enabled` + `crash_reporting_enabled`, default off) is required before any event is delivered, regardless of DSN presence.

### Source builds

Cloning the repo and running without a release build has **no baked DSN**. Error reporting is unavailable unless you set `ATLAS_SENTRY_DSN` locally for development; the first-run consent prompt is hidden when no DSN exists.
