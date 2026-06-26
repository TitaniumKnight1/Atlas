import { getBackendBaseUrl } from "./backend";

export interface ProjectStreamEvent {
  sequence: number;
  topic: string;
  event_type: string;
  project_id: string;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export interface ProjectStreamOptions {
  projectId: string;
  topics?: string[];
  onEvent: (event: ProjectStreamEvent) => void;
  onError?: (error: Event) => void;
}

const DEFAULT_TOPICS = ["server-output", "process-lifecycle", "op-progress"];

export async function connectProjectStream(options: ProjectStreamOptions): Promise<() => void> {
  const baseUrl = await getBackendBaseUrl();
  const topics = options.topics ?? DEFAULT_TOPICS;
  const url = `${baseUrl}/api/v1/projects/${encodeURIComponent(options.projectId)}/stream?topics=${encodeURIComponent(topics.join(","))}`;
  const source = new EventSource(url);

  const handlePayload = (event: MessageEvent<string>) => {
    const parsed = JSON.parse(event.data) as ProjectStreamEvent;
    options.onEvent(parsed);
  };

  for (const topic of topics) {
    source.addEventListener(topic, handlePayload);
  }
  source.addEventListener("heartbeat", handlePayload);
  source.onerror = (error) => {
    options.onError?.(error);
  };

  return () => source.close();
}
