# ADR-0005: Telemetry Sanitizer Boundary

## Status

Accepted

## Context

M2 introduces Atlas application telemetry without allowing FiveM project data, secrets, identifiers, logs, configs, database contents, or player information to leave the user's machine. The privacy boundary must run before any queueing or future Sentry upload.

## Decision

Telemetry defaults to disabled until explicit opt-in. The sanitizer accepts only a narrow Atlas-owned event shape, redacts known secret and identifier patterns, and rejects malformed, unknown, oversized, or FiveM-shaped payloads. Rejections persist only non-sensitive summaries and rule identifiers, never the raw rejected payload.

The Sentry SDK is not added in M2. Delivery is represented by a `TelemetryDeliveryPort` with a local no-op adapter that records skipped delivery attempts; a later dependency-approval pass can add a Sentry adapter behind the same port.

## Consequences

- Disabled telemetry records local rejection summaries and queues nothing.
- Sanitization is deterministic and unit-testable without I/O.
- Privacy wins over debuggability whenever classification is uncertain.
- Queue rows contain only sanitized Atlas application telemetry.
