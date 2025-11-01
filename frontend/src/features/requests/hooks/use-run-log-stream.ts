import { useEffect, useRef, useState } from "react";

import type { RunLogEvent } from "@/lib/api-client";

export type { RunLogEvent } from "@/lib/api-client";

interface UseRunLogStreamOptions {
  enabled?: boolean;
}

export function useRunLogStream(
  requestId: string,
  { enabled = true }: UseRunLogStreamOptions = {}
) {
  const [events, setEvents] = useState<RunLogEvent[]>([]);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    setEvents([]);
    if (!requestId || !enabled) {
      return () => undefined;
    }

    const url = new URL(`/api/runs/${requestId}/logs/stream`, window.location.origin);
    const eventSource = new EventSource(url.toString(), { withCredentials: true });
    sourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as RunLogEvent;
        setEvents((prev) => [...prev, payload]);
      } catch (error) {
        console.error("Failed to parse run log event", error);
      }
    };

    eventSource.onerror = (error) => {
      console.warn("Run log stream closed", error);
      eventSource.close();
    };

    return () => {
      eventSource.close();
      sourceRef.current = null;
    };
  }, [requestId, enabled]);

  return { events };
}
