import { useQuery } from "@tanstack/react-query";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
}

export interface ChatThread {
  id: string;
  request_id: string;
  messages: ChatMessage[];
}

export const chatThreadQueryKey = (requestId: string) => ["chat-thread", requestId] as const;

export function useChatThread(requestId: string) {
  return useQuery({
    queryKey: chatThreadQueryKey(requestId),
    queryFn: async (): Promise<ChatThread> => ({
      id: `${requestId}-thread`,
      request_id: requestId,
      messages: [
        {
          id: "1",
          role: "user",
          content: "Please add retry logic to the loader.",
          created_at: new Date().toISOString()
        }
      ]
    })
  });
}
