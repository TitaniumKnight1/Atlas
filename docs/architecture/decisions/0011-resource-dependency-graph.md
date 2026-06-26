# ADR-0011: Resource Dependency Graph And Manifest Extraction

## Status

Accepted

## Context

M5a builds the resource inventory and dependency graph that M5b lifecycle mutations will depend on. Resource manifests are Lua files; resource names, configs, and manifest snapshots are local FiveM project data.

## Decision

### Manifest extraction (no Lua runtime)

Focused regex/table extraction reads known keys from `fxmanifest.lua` and legacy `__resource.lua`:

- `fx_version` / `resource_manifest_version`
- `game` / `games`
- `version`
- `dependency` / `dependencies` (version suffixes stripped: `ox_lib:3.0.0` → `ox_lib`)
- `provide` / `provides`

Grounded in current Cfx.re resource manifest documentation.

### Graph model

- Directed edges: resource → declared dependency
- Cycle detection: DFS with active stack; no infinite loops on cyclic graphs
- Missing dependencies: edge target not in discovered inventory
- Conflicts: duplicate resource names; duplicate `provide` names across resources
- Topological order: Kahn's algorithm; refused when cycles exist

### M5a / M6 health seam (ADR-0007)

M5a exposes resource health as inventory query data (manifest validity, dependency satisfaction, enabled/disabled inference from `server.cfg` ensure lines). It defines health snapshots as a future metric source for M6 but does not build collectors, dashboards, or historical graphs.

## Consequences

- M5b install/enable operations must consult the graph before mutating files or `server.cfg`.
- Manifest extraction may miss dynamic Lua-generated manifest values; findings mark invalid manifests explicitly.
