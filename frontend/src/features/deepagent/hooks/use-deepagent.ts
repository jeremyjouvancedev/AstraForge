import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ensureCsrfToken } from "@/lib/api-client";

const API_BASE = "/api";

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()!.split(";").shift() ?? null;
  return null;
}

export interface DeepAgentChunk {
  messages?: { role: string; content: string }[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
}

export interface DeepAgentConversation {
  conversation_id: string;
  sandbox_session_id: string;
  status: string;
}

export interface DeepAgentMessage {
  id: string;
  role: string;
  content: string;
  created_at: string;
}

export function useCreateConversation() {
  return useMutation<DeepAgentConversation, Error, void>({
    mutationFn: async () => {
      await ensureCsrfToken();
      const csrfToken = getCookie("csrftoken") ?? "";
      const response = await fetch(`${API_BASE}/deepagent/conversations/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken
        },
        credentials: "include",
        body: JSON.stringify({})
      });
      if (!response.ok) {
        throw new Error("Failed to create deep agent conversation");
      }
      return (await response.json()) as DeepAgentConversation;
    }
  });
}

export function useSendDeepAgentMessage(conversationId: string) {
  const queryClient = useQueryClient();
  return useMutation<void, Error, { content: string; onChunk: (chunk: DeepAgentChunk) => void }>({
    mutationFn: async ({ content, onChunk }) => {
      await ensureCsrfToken();
      const csrfToken = getCookie("csrftoken") ?? "";
      const response = await fetch(
        `${API_BASE}/deepagent/conversations/${conversationId}/messages/`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken
          },
          credentials: "include",
          body: JSON.stringify({
            messages: [{ role: "user", content }],
            stream: true
          })
        }
      );
      if (!response.ok || !response.body) {
        throw new Error("Failed to send message to deep agent");
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let done = false;
      // basic SSE line parsing
      while (!done) {
        const result = await reader.read();
        done = result.done ?? false;
        if (done || !result.value) break;
        buffer += decoder.decode(result.value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          const jsonPayload = line.slice(5).trim();
          if (!jsonPayload) continue;
          try {
            const parsed = JSON.parse(jsonPayload);
            onChunk(parsed);
          } catch {
            // ignore malformed chunks
          }
        }
      }
      // refresh any cached state keyed by this conversation if needed later
      queryClient.invalidateQueries({ queryKey: ["deepagent", conversationId] });
    }
  });
}
