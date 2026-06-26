import { useEffect, useState } from "react";

import { getHealth, runSqliteSmoke, type HealthData, type SqliteSmokeData } from "../api/backend";
import "./App.css";

type BackendStatus =
  | { state: "loading" }
  | { state: "ready"; health: HealthData; sqliteSmoke: SqliteSmokeData }
  | { state: "error"; message: string };

export function App() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>({ state: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function loadBackendStatus() {
      try {
        const health = await getHealth();
        const sqliteSmoke = await runSqliteSmoke();
        if (!cancelled) {
          setBackendStatus({ state: "ready", health, sqliteSmoke });
        }
      } catch (error) {
        if (!cancelled) {
          setBackendStatus({
            state: "error",
            message: error instanceof Error ? error.message : "Unknown backend error"
          });
        }
      }
    }

    void loadBackendStatus();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="app-shell">
      <section className="hero">
        <p className="eyebrow">Atlas M0a</p>
        <h1>Desktop walking skeleton</h1>
        <p>
          Tauri is supervising an embedded FastAPI backend and the React app is calling a real
          loopback HTTP endpoint.
        </p>
      </section>

      <section className="status-card" aria-live="polite">
        {backendStatus.state === "loading" ? <p>Waiting for backend readiness...</p> : null}

        {backendStatus.state === "error" ? (
          <>
            <h2>Backend unavailable</h2>
            <p>{backendStatus.message}</p>
          </>
        ) : null}

        {backendStatus.state === "ready" ? (
          <>
            <h2>Backend health: {backendStatus.health.status}</h2>
            <dl>
              <div>
                <dt>Transport</dt>
                <dd>{backendStatus.health.transport}</dd>
              </div>
              <div>
                <dt>SQLite journal mode</dt>
                <dd>{backendStatus.sqliteSmoke.journal_mode}</dd>
              </div>
              <div>
                <dt>SQLite round trip</dt>
                <dd>{backendStatus.sqliteSmoke.round_tripped_value}</dd>
              </div>
              <div>
                <dt>Database path</dt>
                <dd>{backendStatus.health.database_path}</dd>
              </div>
            </dl>
          </>
        ) : null}
      </section>
    </main>
  );
}
