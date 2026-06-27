import { useEffect, useState } from "react";

import { getHealth, type HealthData } from "../api/backend";

export type BackendConnectionState = "connecting" | "ready" | "down";

export interface BackendStatus {
  state: BackendConnectionState;
  health?: HealthData;
  message: string;
}

export function useBackendStatus(pollMs = 5000): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>({
    state: "connecting",
    message: "Connecting to local backend"
  });

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    async function checkHealth() {
      try {
        const health = await getHealth();
        if (!cancelled) {
          setStatus({
            state: "ready",
            health,
            message: `${health.service} ready`
          });
        }
      } catch {
        if (!cancelled) {
          setStatus({
            state: "down",
            message: "Local backend is unavailable"
          });
        }
      } finally {
        if (!cancelled) {
          timer = window.setTimeout(checkHealth, pollMs);
        }
      }
    }

    void checkHealth();
    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, [pollMs]);

  return status;
}
