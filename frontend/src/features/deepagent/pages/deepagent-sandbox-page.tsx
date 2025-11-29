import { useEffect, useMemo, useRef, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ChatTimeline } from "@/features/chat/components/chat-timeline";
import {
  DeepAgentChunk,
  DeepAgentConversation,
  DeepAgentMessage,
  useCreateConversation,
  useSendDeepAgentMessage
} from "@/features/deepagent/hooks/use-deepagent";

export default function DeepAgentSandboxPage() {
  const [conversation, setConversation] = useState<DeepAgentConversation | null>(null);
  const [messages, setMessages] = useState<DeepAgentMessage[]>([]);
  const [input, setInput] = useState("");
  const [sandboxImageUrl, setSandboxImageUrl] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const messageIdRef = useRef(0);

  const createConversation = useCreateConversation();
  const sendMessageMutation = useSendDeepAgentMessage(conversation?.conversation_id ?? "");

  useEffect(() => {
    if (!conversation && !createConversation.isPending && !createConversation.isSuccess) {
      createConversation.mutate(undefined, {
        onSuccess: (conv) => {
          setConversation(conv);
        }
      });
    }
  }, [conversation, createConversation]);

  const handleChunk = (chunk: DeepAgentChunk) => {
    const errorText =
      typeof chunk.error === "string"
        ? chunk.error
        : null;
    if (errorText) {
      const normalized =
        errorText.includes("context_length_exceeded") ||
        errorText.toLowerCase().includes("context length")
          ? "The deep agent request exceeded the model's context window. Try clearing the conversation or shortening your prompt or attached content.\n\nDetails:\n" +
            errorText
          : errorText;
      messageIdRef.current += 1;
      const errorMessage: DeepAgentMessage = {
        id: String(messageIdRef.current),
        role: "system",
        content: normalized,
        created_at: new Date().toISOString()
      };
      setMessages((prev) => [...prev, errorMessage]);
      return;
    }

    // DeepAgents returns a state-like object; look for messages array
    const chunkMessages = chunk?.messages;
    if (!Array.isArray(chunkMessages)) return;
    const latest = chunkMessages[chunkMessages.length - 1];
    if (!latest || typeof latest.content !== "string") return;
    messageIdRef.current += 1;
    const synthetic: DeepAgentMessage = {
      id: String(messageIdRef.current),
      role: latest.role ?? "assistant",
      content: latest.content,
      created_at: new Date().toISOString()
    };
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.role === synthetic.role && last.content === synthetic.content) {
        return prev;
      }
      return [...prev, synthetic];
    });
  };

  const handleSend = async () => {
    if (!input.trim() || !conversation || sendMessageMutation.isPending) return;
    messageIdRef.current += 1;
    const userMessage: DeepAgentMessage = {
      id: String(messageIdRef.current),
      role: "user",
      content: input,
      created_at: new Date().toISOString()
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsStreaming(true);
    try {
      await sendMessageMutation.mutateAsync({ content: userMessage.content, onChunk: handleChunk });
    } finally {
      setIsStreaming(false);
      // attempt to refresh screenshot after each turn
      if (conversation) {
        const url = `/api/sandbox/sessions/${conversation.sandbox_session_id}/screenshot`;
        setSandboxImageUrl(`${url}?t=${Date.now()}`);
      }
    }
  };

  const sandboxHint = useMemo(() => {
    if (!conversation) return "Provisioning sandbox...";
    if (!sandboxImageUrl) {
      return "No screenshot yet. Send a message and we will attempt to capture the sandbox.";
    }
    return "";
  }, [conversation, sandboxImageUrl]);

  return (
    <div className="flex h-full w-full min-h-0 flex-col gap-4 p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.35em] text-muted-foreground">
            Deep Agent Sandbox
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-foreground">Sandbox Conversations</h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Talk to a deep agent on the left while previewing its sandbox environment on the right.
          </p>
        </div>
      </header>

      <div className="grid flex-1 min-h-0 gap-4 lg:grid-cols-2">
        <Card className="flex min-h-0 flex-1 flex-col border-border/70 bg-card/95">
          <CardHeader className="border-b border-border/60">
            <CardTitle className="text-sm font-semibold">Conversation</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-1 min-h-0 flex-col gap-4 p-4">
            <div className="flex-1 min-h-0 overflow-y-auto rounded-xl bg-muted/40 p-3">
              <ChatTimeline messages={messages} />
            </div>
            <form
              className="flex gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                void handleSend();
              }}
            >
              <Input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Ask the deep agent to inspect or modify files in the sandbox..."
                disabled={!conversation || isStreaming}
              />
              <Button type="submit" disabled={!conversation || isStreaming || !input.trim()}>
                {isStreaming ? "Streaming..." : "Send"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card className="flex min-h-0 flex-1 flex-col border-border/70 bg-card/95">
          <CardHeader className="border-b border-border/60">
            <CardTitle className="text-sm font-semibold">Sandbox Preview</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col p-4">
            {sandboxHint && (
              <p className="mb-3 text-xs text-muted-foreground">
                {sandboxHint}
              </p>
            )}
            <div className="relative flex flex-1 items-center justify-center overflow-hidden rounded-xl border border-dashed border-border/70 bg-muted/40">
              {sandboxImageUrl ? (
                <img
                  src={sandboxImageUrl}
                  alt="Sandbox preview"
                  className="h-full w-full object-contain"
                />
              ) : (
                <div className="flex flex-col items-center gap-2 text-xs text-muted-foreground">
                  <span>Sandbox live view is not yet available.</span>
                  <span className="text-[10px] uppercase tracking-[0.3em]">
                    Screenshot endpoint /screenshot will be used when implemented
                  </span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
