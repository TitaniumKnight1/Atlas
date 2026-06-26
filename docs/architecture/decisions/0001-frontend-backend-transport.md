# 0001: Frontend-Backend Transport

## Status

Accepted for M0a.

## Context

Atlas runs a React frontend inside a Tauri WebView and a local FastAPI backend as an embedded sidecar. The Phase 7 roadmap left the frontend-backend transport open between Tauri IPC and loopback HTTP. M0a must prove the risky desktop assumptions with one real backend endpoint, clean lifecycle management, bundled CI output, and a minimal SQLite smoke from the correct app-data location.

## Decision

Atlas will use loopback HTTP between the React frontend and the embedded FastAPI backend.

The Tauri core process owns backend lifecycle and exposes only the backend base URL to the frontend. The frontend typed API client calls FastAPI over `http://127.0.0.1:<port>`. The backend binds to loopback only and chooses an ephemeral port during startup. Tauri waits for a stdout readiness handshake before allowing the frontend to call the backend.

## Rationale

- FastAPI is HTTP-native, so loopback HTTP proves the actual backend boundary instead of duplicating backend routes as Rust IPC commands.
- The same route can be exercised by pytest smoke tests, frontend fetch calls, and future OpenAPI contract tooling.
- Future streams can use HTTP-friendly transports such as SSE or WebSocket without redesigning the command/query boundary.
- Tauri remains responsible for native windowing, permissions, app-data path resolution, startup handshake, and clean process shutdown.

## Rejected Alternative: Tauri IPC

Tauri IPC was rejected for M0a because it would require Rust command wrappers around FastAPI behavior or a hybrid bridge. That would add another API surface before Atlas has proven the Python sidecar packaging and lifecycle risks. IPC may still be useful later for shell-owned native operations, but it should not replace the local backend API boundary.

## Consequences

- The backend must never bind to a public interface.
- The frontend must discover the base URL from Tauri instead of hard-coding a port.
- Tauri must handle startup timeout, port readiness, graceful shutdown, and forced cleanup so loopback ports are not left bound.
- The HTTP client boundary lives under `frontend/src/api/` and remains the only frontend access path to backend data.
