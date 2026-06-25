# Testing Strategy

Phase 4 defines the testing approach and future layout only. **No test source code or test config files are created in this phase.**

## Testing Goals

- Prove hexagonal boundaries are respected (domain without I/O, adapters with integration tests).
- Protect privacy boundaries (telemetry sanitizer, incident export redaction).
- Ensure developer-first workflows (dry-run, diff, undo) behave correctly end-to-end.
- Keep critical FiveM lifecycle paths reliable: import, validate, resource change, backup, incident capture.

## Test Pyramid

| Layer | Tool | Scope |
| --- | --- | --- |
| Domain unit | pytest | Policies, fingerprinting, validation rules, automation conditions |
| Application unit | pytest | Command/query orchestration with mocked ports |
| Adapter integration | pytest | Filesystem, Git, process, persistence adapters |
| API contract | pytest + HTTP client | Routes, schemas, stream behavior |
| Frontend component | Vitest or React Testing Library (deferred) | UI components and hooks |
| End-to-end | Playwright | Critical user workflows through Tauri shell |

## Future Directory Layout

When tests are introduced:

```
tests/
  unit/
    domain/
    application/
  integration/
    adapters/
    api/
  e2e/
    workflows/
  fixtures/
    sample-projects/
```

- `tests/fixtures/sample-projects/` holds minimal synthetic FiveM project trees for integration tests.
- Never commit real user servers, player data, or production secrets to fixtures.

## What To Test Per Subsystem

- **Project / Setup**: project import, artifact pin, validation preflight.
- **Resources / Config**: dry-run diffs, snapshot creation, rollback semantics.
- **Git**: status detection, conflict warnings, commit attribution in incidents.
- **Backup**: create, verify, restore, retention enforcement.
- **Monitoring**: metric subscription lifecycle (mocked process output).
- **Incident Intelligence**: fingerprint stability, deduplication, Markdown export structure.
- **Automation**: trigger matching, approval gates, idempotent scheduler jobs.
- **Telemetry**: sanitizer rejects FiveM data; opt-out disables upload.
- **Plugins**: capability denial, trust gating, audit events on enable/disable.

## CI Integration

Described in [ci-cd-strategy.md](./ci-cd-strategy.md). Tests will run on pull requests once workflows and dependencies exist.

## Explicitly Out Of Scope (Phase 4)

- `tests/` directory with test files
- `pytest.ini`, `conftest.py`, Playwright config
- Coverage thresholds and CI enforcement

## Open Questions

- Whether E2E tests run against a real FXServer in CI or use mocked process adapters.
- Minimum fixture project needed to represent txAdmin + resources + Git sanely.
- Whether frontend unit tests share the backend test fixtures or use API mocks only.
