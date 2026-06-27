# ADR-0005: Telemetry Sanitizer Boundary

## Status

Accepted

## Context

M2 introduces Atlas application telemetry without allowing FiveM project data, secrets, identifiers, logs, configs, database contents, or player information to leave the user's machine. The privacy boundary must run before any queueing or future Sentry upload.

## Decision

Telemetry defaults to disabled until explicit opt-in. The sanitizer accepts only a narrow Atlas-owned event shape, redacts known secret and identifier patterns, and rejects malformed, unknown, oversized, or FiveM-shaped payloads. Rejections persist only non-sensitive summaries and rule identifiers, never the raw rejected payload.

The Sentry SDK is not added in M2. Delivery is represented by a `TelemetryDeliveryPort` with a local no-op adapter that records skipped delivery attempts; a later dependency-approval pass can add a Sentry adapter behind the same port.

Before any real Sentry transport replaces the no-op delivery adapter, an independent adversarial audit of `backend/adapters/telemetry/sanitizer.py` by someone other than the original author must pass. Telemetry remains disabled by default until that audit passes and the Sentry transport is explicitly approved.

**M7c export sanitizer (second deliberate outbound path):** User-initiated incident Markdown export is a separate, higher-risk outbound path than telemetry because the user explicitly copies sanitized content into uncontrolled third-party AI tools. `backend/domain/incident/export_sanitizer.py` reuses the M2 `SECRET_RULES` / `IDENTIFIER_RULES` vocabulary but applies a **redact-in-place** policy (not fail-closed). An **independent adversarial audit** of the export sanitizer by a different author/model was completed. The export sanitizer is **audited + passing** — it does not claim to be perfectly leak-proof, but has passed rigorous independent validation.

The same two audit questions apply to both sanitizers:

- Whether sanitizer confidence should be primarily structure-based or blocklist-based.
- Whether free-text and stack-trace fields should redact in place or fail closed when they contain suspicious content.

## Consequences

- Disabled telemetry records local rejection summaries and queues nothing.
- Sanitization is deterministic and unit-testable without I/O.
- Privacy wins over debuggability whenever classification is uncertain (telemetry). Export errs toward redaction per-value but preserves surrounding debug context.
- Queue rows contain only sanitized Atlas application telemetry.
- Incident exports store only sanitized Markdown files plus redaction summaries — never unsanitized copies.
