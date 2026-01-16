import { useState, useEffect, useCallback, useRef } from 'react';
import { 
    createAstraControlSession, 
    resumeAstraControlSession, 
    fetchAstraControlSession,
    fetchAstraControlSessions,
    cancelAstraControlSession,
    sendAstraControlMessage
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
      reasoning_effort?: string,
      validation_required?: boolean
    ) => {
      return createAstraControlSession({ 
        goal, 
        model,
        provider,
        reasoning_check,
        reasoning_effort,
        validation_required
      });
    }, []);
  
    const resumeSession = useCallback(async () => {
      if (!sessionId) return;
      return resumeAstraControlSession(sessionId);
    }, [sessionId]);
  
    const cancelSession = useCallback(async () => {
      if (!sessionId) return;
      return cancelAstraControlSession(sessionId);
    }, [sessionId]);
  
      const sendMessage = useCallback(async (message: string, validation_required?: boolean) => {
        if (!sessionId) return;
        return sendAstraControlMessage(sessionId, message, validation_required);
      }, [sessionId]);
        return { events, status, startSession, resumeSession, cancelSession, sendMessage, fetchSessions };
  }
  