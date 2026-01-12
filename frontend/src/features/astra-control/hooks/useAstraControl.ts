import { useState, useEffect, useCallback, useRef } from 'react';
import { 
  createAstraControlSession, 
  resumeAstraControlSession, 
  fetchAstraControlSession,
  fetchAstraControlSessions
} from '@/lib/api-client';
import { type AgentEvent } from '../types';

export function useAstraControl(sessionId: string | null) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [status, setStatus] = useState<string>('idle');
  const lastProcessedIndex = useRef<number>(-1);

  const fetchSessions = useCallback(async () => {
    return fetchAstraControlSessions();
  }, []);

  useEffect(() => {
    if (!sessionId) {
      setEvents([]);
      setStatus('idle');
      lastProcessedIndex.current = -1;
      return;
    }

    // Reset state for new session
    setEvents([]);
    setStatus('running');
    lastProcessedIndex.current = -1;

    let isMounted = true;

    const poll = async () => {
      try {
        const session = await fetchAstraControlSession(sessionId);
        if (!isMounted) return;

        if (session.status) {
          setStatus(session.status);
        }

        const backendEvents = session.state?.events || [];
        if (backendEvents.length > lastProcessedIndex.current + 1) {
          const newEvents: AgentEvent[] = [];
          for (let i = lastProcessedIndex.current + 1; i < backendEvents.length; i++) {
            const data = backendEvents[i];
            newEvents.push({
              type: Object.keys(data)[0],
              payload: Object.values(data)[0] as Record<string, unknown>,
              timestamp: Date.now()
            });
          }
          setEvents((prev) => [...prev, ...newEvents]);
          lastProcessedIndex.current = backendEvents.length - 1;
        }

        // Stop polling if session is finished
        if (['completed', 'failed'].includes(session.status)) {
          clearInterval(pollInterval);
        }
      } catch (err) {
        console.error("Polling failed:", err);
      }
    };

    // Initial poll
    poll();

    // Set up interval
    const pollInterval = setInterval(poll, 2000);

    return () => {
      isMounted = false;
      clearInterval(pollInterval);
    };
  }, [sessionId]);

  const startSession = useCallback(async (
    goal: string, 
    model?: string,
    provider?: string,
    reasoning_check?: boolean,
    reasoning_effort?: string
  ) => {
    return createAstraControlSession({ 
      goal, 
      model,
      provider,
      reasoning_check,
      reasoning_effort
    });
  }, []);

  const resumeSession = useCallback(async () => {
    if (!sessionId) return;
    return resumeAstraControlSession(sessionId);
  }, [sessionId]);

  return { events, status, startSession, resumeSession, fetchSessions };
}