# Naming Conventions

Atlas naming should make module boundaries, dependency direction, and privacy boundaries obvious in both code and repository paths.

## Repository Paths

- Use lowercase kebab-case for multi-word documentation paths: `docs/standards/`, `plugin-sdk/contribution-points/`.
- Use lowercase single-word slugs for bounded-context modules: `backend/domain/project/`, `backend/application/incident/`.
- Mirror the same module slug across `domain/`, `application/`, and `frontend/src/features/` where a UI slice exists.
- Adapter directories use integration names, not module names: `backend/adapters/fivem/`, not `backend/adapters/setup/`.
- Do not create screen-only folders such as `pages/settings/` without a corresponding bounded context.

## Python

- Packages and modules: `snake_case`.
- Classes: `PascalCase`.
- Functions, methods, variables: `snake_case`.
- Constants: `SCREAMING_SNAKE_CASE`.
- Domain events: past-tense `PascalCase` names matching architecture examples (`ResourceUpdated`, `IncidentCreated`).
- Commands: imperative verb phrases (`UpdateResource`, `CreateBackup`).
- Queries: noun phrases (`ListIncidents`, `GetProjectStatus`).
- Port interfaces: suffix with `Port` (`FilesystemPort`, `GitPort`).
- Adapter implementations: suffix with `Adapter` (`SqlAlchemyProjectRepository`, `GitPythonAdapter`).
- API schema modules live under `backend/api/schemas/` and use suffix `Schema` or `DTO` consistently within a module.

## TypeScript / React

- React components: `PascalCase` file and export names (`IncidentTimeline.tsx`).
- Hooks: `use` prefix (`useProjectStatus`).
- Non-component modules: `camelCase` or `kebab-case` file names; pick one style per folder and stay consistent.
- Feature folders under `frontend/src/features/` use the same slugs as backend modules.
- Shared components under `frontend/src/components/` must not encode feature-specific business rules in their names.

## API Routes

- Use plural resource nouns for collections: `/projects`, `/incidents`, `/automations`.
- Use verbs only for command endpoints when a REST noun is misleading: `/commands/dry-run`, `/streams/console`.
- Stream endpoints should indicate purpose: `/streams/metrics`, `/streams/incidents`.
- Version API routes under `/api/v1/` when versioning becomes necessary.

## Plugin SDK

- Plugin package identifiers: reverse-DNS style (`com.example.atlas.validator`).
- Contribution point folder names match manifest keys in `plugin-sdk/contribution-points/`.
- Capability identifiers: `kebab-case` (`read-project-metadata`, `execute-process-commands`).
- Manifest fields: `camelCase` in JSON.

## Events, Auditing, and Telemetry

- Domain events: `PascalCase` past tense.
- Audit action names: `snake_case` verbs (`resource_updated`, `backup_restored`).
- Telemetry event names: `atlas.<subsystem>.<failure>` (e.g., `atlas.backend.startup_failed`).
- Never name telemetry events after FiveM project entities in a way that encourages uploading project data.

## Open Questions

- Should frontend feature folders use `incidents` or `incident` to match backend `incident/`? Current scaffold uses `incidents` for the UI slice and `incident` for backend domain slug.
- Should API routes be grouped by module (`/resources/...`) or by operation type (`/commands/...`, `/queries/...`)?
