import { useMemo, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChatComposer } from "@/features/chat/components/chat-composer";
import { ChatTimeline } from "@/features/chat/components/chat-timeline";
import { ChatThread, chatThreadQueryKey, useChatThread } from "@/features/chat/hooks/use-chat-thread";
import { cn } from "@/lib/cn";
import { useQueryClient } from "@tanstack/react-query";

interface RunChatPanelProps {
  requestId: string;
  className?: string;
}

export function RunChatPanel({ requestId, className }: RunChatPanelProps) {
  const queryClient = useQueryClient();
  const { data, isLoading } = useChatThread(requestId);
  const [draft, setDraft] = useState("");

  const conversation = useMemo(() => data?.messages ?? [], [data?.messages]);

  const handleSend = (message: string) => {
    if (!message.trim()) {
      return;
    }

    const timestamp = new Date().toISOString();
    const id = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}`;

    queryClient.setQueryData(chatThreadQueryKey(requestId), (current: unknown) => {
      const existing = current as ChatThread | undefined;
      const currentThread: ChatThread = existing ?? {
        id: `${requestId}-thread`,
        request_id: requestId,
        messages: [],
      };

      return {
        ...currentThread,
        messages: [
          ...currentThread.messages,
          {
            id,
            role: "user" as const,
            content: message,
            created_at: timestamp,
          },
        ],
      };
    });

    setDraft("");
  };

  return (
    <Card className={cn("flex h-full flex-col", className)}>
      <CardHeader className="space-y-1">
        <CardTitle className="text-base">Workspace Chat</CardTitle>
        <p className="text-xs text-muted-foreground">
          Talk to Codex about this run. Messages stay attached to the current session.
        </p>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4">
        <div className="flex-1 overflow-hidden rounded-md border border-zinc-800/60 bg-zinc-950/60">
          <div className="h-full overflow-y-auto p-4">
            {isLoading ? <p className="text-sm text-muted-foreground">Loading conversation…</p> : <ChatTimeline messages={conversation} />}
          </div>
        </div>
        <ChatComposer
          onSend={handleSend}
          placeholder="Ask Codex to keep going…"
          value={draft}
          onChange={setDraft}
        />
      </CardContent>
    </Card>
  );
}
