# Data Flow

Atlas data flow is designed around explicit intent, local execution, auditability, and privacy. The frontend requests plans; the backend evaluates risk; the user approves; adapters perform work; events update local state; incidents and audit records preserve context.

## Primary Command Flow

```mermaid
sequenceDiagram
    participant User
    participant UI as React UI
    participant API as FastAPI Command Endpoint
    participant Service as Application Service
    participant Policy as Domain Policy
    participant Adapter as Adapter
    participant DB as SQLite
    participant Bus as Event Bus
    User->>UI: Choose action
    UI->>API: Request dry run
    API->>Service: Build plan
    Service->>Policy: Evaluate rules and risks
    Service->>Adapter: Inspect current state
    Service->>DB: Store pending plan
    API-->>UI: Return plan, diff, undo route
    User->>UI: Approve
    UI->>API: Execute approved plan
    API->>Service: Execute command
    Service->>Adapter: Apply changes
    Service->>DB: Commit state and audit event
    Service->>Bus: Publish domain event
    Bus-->>UI: Stream progress update
```

## Incident Data Flow

```mermaid
flowchart LR
    ConsoleLogs[Console Logs] --> IncidentCollector[Incident Collector]
    ProcessExit[Process Exit] --> IncidentCollector
    ValidationFailure[Validation Failure] --> IncidentCollector
    AutomationFailure[Automation Failure] --> IncidentCollector
    IncidentCollector --> Sanitizer[Local Project Snapshot Filter]
    Sanitizer --> Fingerprinter[Fingerprinting]
    Fingerprinter --> IncidentStore[(SQLite Incident Store)]
    IncidentStore --> Timeline[Timeline And Related Incidents]
    Timeline --> MarkdownExport[Manual Markdown Export]
```

Incident data remains local. The local project snapshot filter is not the Atlas Sentry telemetry sanitizer; it prepares safe, relevant local incident context for the user's own viewing and manual export.

## Telemetry Data Flow

```mermaid
flowchart LR
    AtlasError[Atlas App Error] --> TelemetryPolicy[Telemetry Enabled Check]
    TelemetryPolicy --> Sanitizer[SDK Side Sanitizer]
    Sanitizer --> Classifier{Contains FiveM Project Data}
    Classifier -->|Yes| Reject[Reject Event Locally]
    Classifier -->|No| Sentry[Sentry Atlas Project]
```

Telemetry is for Atlas application failures only. FiveM logs, configs, resources, databases, player data, and identifiers are never valid telemetry payloads.

## Local Storage Classes

- Durable metadata: SQLite.
- Large immutable backups: user-selected backup directory.
- Project source/config/resources: original project filesystem.
- Runtime logs: source locations plus optional indexed references.
- Markdown exports: user-chosen save location.

## Concurrency Rules

- UI interactions are optimistic only after a backend plan exists.
- Long-running operations emit progress events and can be cancelled when adapters support cancellation.
- SQLite writes are short and controlled by a Unit of Work.
- Scheduler actions must use stable IDs and idempotency keys to avoid duplicate runs.
