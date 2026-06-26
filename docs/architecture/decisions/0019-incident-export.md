# ADR-0019: M7c Incident Markdown Export and Export Sanitizer

## Status

Accepted

## Context

M7c completes Incident Intelligence by producing an AI-optimized Markdown report users manually copy into external AI tools. This is the **most privacy-critical** milestone: exports aggregate config references, log tails, git state, runtime snapshots, and grouping metadata — all potentially secret-bearing.

ADR-0005 established telemetry sanitization (fail-closed). Export is a **second deliberate outbound path** with higher user-driven risk.

## Decision

### Single sanitized export path

- Exactly one export API: `POST /api/v1/projects/{project_id}/incidents/{group_id}/exports/markdown`.
- Flow: assemble Markdown from M7a snapshots + M7b group data → **always** run export sanitizer → write sanitized file → return sanitized Markdown + redaction summary.
- **No raw/unsanitized export option** exists. Local UI inspection of full incident data is not this export path.

### Sanitizer policy (differs from telemetry)

| Aspect | Telemetry (M2) | Export (M7c) |
| --- | --- | --- |
| Policy | Fail-closed / drop event | Redact-in-place |
| Markers | `[REDACTED]` | `[REDACTED: category]` |
| Uncertainty | Reject payload | Redact individual value |
| Vocabulary | `SECRET_RULES`, `IDENTIFIER_RULES` | **Reused** + export-only credential URL / player / unknown-secret rules |

Pure function: `sanitize_export_markdown(markdown) -> ExportSanitizationResult`.

### Report assembly

Structured sections: privacy notice, summary, fingerprint/grouping (with over-grouping review when `occurrence_count > 1`), per-occurrence timeline (exit code, message, log excerpts), environment, resources, startup order, config references (metadata only).

### Persistence

`incident_exports` stores export metadata, **sanitized** file path, content hash, and redaction summary. No unsanitized copy.

### Audit gate (unproven until independent review)

The export sanitizer is **not claimed leak-proof**. It requires an independent adversarial audit (different author/model) per ADR-0005 family before end-user reliance. Unit/integration adversarial tests in-repo are necessary but not sufficient.

## Consequences

- Users can debug crashes with external AI without Atlas calling any AI API.
- Over-redaction is acceptable; leaking is not.
- M7 (Incident Intelligence) is complete after M7c.
