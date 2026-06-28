import { useEffect, useState } from "react";

import { connectProjectStream, type ProjectStreamEvent } from "../api/stream";

/** Stable string key so inline topic arrays do not retrigger the stream effect every render. */
export function serializeStreamTopics(topics: readonly string[]): string {
  return topics.join(",");
}

export function parseStreamTopics(topicKey: string): string[] {
  return topicKey ? topicKey.split(",") : [];
}

export function useProjectStream(projectId: string | null, topics: string[] = ["server-output"]) {
  const [events, setEvents] = useState<ProjectStreamEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const topicKey = serializeStreamTopics(topics);

  useEffect(() => {
    if (!projectId) {
      setEvents([]);
      setConnected(false);
      return;
    }

    let cancelled = false;
    let disconnect: (() => void) | undefined;
    const activeTopics = parseStreamTopics(topicKey);

    void connectProjectStream({
      projectId,
      topics: activeTopics,
      onEvent: (event) => {
        if (cancelled) {
          return;
        }
        setConnected(true);
        setEvents((current) => [...current.slice(-199), event]);
      }
    }).then((close) => {
      if (cancelled) {
        close();
        return;
      }
      disconnect = close;
    });

    return () => {
      cancelled = true;
      disconnect?.();
      setConnected(false);
    };
  }, [projectId, topicKey]);

  return { events, connected };
}
