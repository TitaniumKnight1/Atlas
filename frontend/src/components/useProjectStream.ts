import { useEffect, useMemo, useState } from "react";

import { connectProjectStream, type ProjectStreamEvent } from "../api/stream";

export function useProjectStream(projectId: string | null, topics: string[] = ["server-output"]) {
  const [events, setEvents] = useState<ProjectStreamEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const topicKey = useMemo(() => topics.join(","), [topics]);

  useEffect(() => {
    if (!projectId) {
      setEvents([]);
      setConnected(false);
      return;
    }

    let cancelled = false;
    let disconnect: (() => void) | undefined;

    void connectProjectStream({
      projectId,
      topics,
      onEvent: (event) => {
        if (cancelled) {
          return;
        }
        setConnected(true);
        setEvents((current) => [...current.slice(-199), event]);
      }
    }).then((close) => {
      disconnect = close;
    });

    return () => {
      cancelled = true;
      disconnect?.();
      setConnected(false);
    };
  }, [projectId, topicKey, topics]);

  return { events, connected };
}
