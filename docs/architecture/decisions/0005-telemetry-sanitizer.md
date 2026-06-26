# ADR-0005: Telemetry Sanitizer Boundary

## Status

Accepted

## Context

M2 introduces Atlas application telemetry without allowing FiveM project data, secrets, identifiers, logs, configs, database contents, or player information to leave the user's machine. The privacy boundary must run before any queueing or future Sentry upload.

## Decision

Telemetry defaults to disabled until explicit opt-in. The sanitizer accepts only a narrow Atlas-owned event shape, redacts known secret and identifier patterns, and rejects malformed, unknown, oversized, or FiveM-shaped payloads. Rejections persist only non-sensitive summaries and rule identifiers, never the raw rejected payload.

The Sentry SDK is not added in M2. Delivery is represented by a `TelemetryDeliveryPort` with a local no-op adapter that records skipped delivery attempts; a later dependency-approval pass can add a Sentry adapter behind the same port.

Before any real Sentry transport replaces the no-op delivery adapter, an independent adversarial audit of `backend/adapters/telemetry/sanitizer.py` by someone other than the original author must pass. Telemetry remains disabled by default until that audit passes and the Sentry transport is explicitly approved.

Two audit questions remain open for that gate:

- Whether sanitizer confidence should be primarily structure-based or blocklist-based.
- Whether free-text and stack-trace fields should redact in place or fail closed when they contain suspicious content.

## Consequences

- Disabled telemetry records local rejection summaries and queues nothing.
- Sanitization is deterministic and unit-testable without I/O.
- Privacy wins over debuggability whenever classification is uncertain.
- Queue rows contain only sanitized Atlas application telemetry.
