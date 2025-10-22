import { useQuery } from "@tanstack/react-query";

interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
}

interface ChatThread {
  id: string;
  request_id: string;
  messages: ChatMessage[];
}

export function useChatThread(requestId: string) {
  return useQuery({
    queryKey: ["chat-thread", requestId],
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
