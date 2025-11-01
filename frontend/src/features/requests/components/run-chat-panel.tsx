import { useEffect, useMemo, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChatComposer } from "@/features/chat/components/chat-composer";
import { ChatTimeline } from "@/features/chat/components/chat-timeline";
import { cn } from "@/lib/cn";
import { sendChatMessage } from "@/lib/api-client";
import { useMutation, useQueryClient } from "@tanstack/react-query";

interface RunChatPanelProps {
  requestId: string;
  history?: string | null;
  storedMessages?: Array<Record<string, unknown>> | null;
  className?: string;
}

type TimelineRole = "user" | "assistant" | "system";

interface TimelineMessage {
  id: string;
  role: TimelineRole;
  content: string;
  created_at: string;
}

function parseIsoTimestamp(value: unknown, fallbackIndex: number): string {
  if (typeof value === "string" && value.trim()) {
    const parsed = Date.parse(value);
    if (!Number.isNaN(parsed)) {
      return new Date(parsed).toISOString();
    }
    return value;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return new Date(value).toISOString();
  }
  return new Date(Date.now() + fallbackIndex).toISOString();
}

function safeRole(value: unknown): TimelineRole {
  if (typeof value === "string") {
    const normalized = value.toLowerCase();
    if (normalized === "user" || normalized === "assistant" || normalized === "system") {
      return normalized;
    }
  }
  return "assistant";
}

function parseHistory(history: string | null | undefined): TimelineMessage[] {
  if (!history) {
    return [];
  }
  const lines = history.split(/\r?\n/);
  const messages: TimelineMessage[] = [];
  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    try {
      const record = JSON.parse(trimmed);
      const role = safeRole(record.role ?? record.author ?? record.type);
      const content =
        typeof record.content === "string"
          ? record.content
          : typeof record.message === "string"
          ? record.message
          : "";
      if (!content) return;
      const createdAt = parseIsoTimestamp(record.created_at ?? record.timestamp, index);
      const identifier = String(record.id ?? `history-${index}`);
      messages.push({
        id: identifier,
        role,
        content,
        created_at: createdAt,
      });
    } catch {
      messages.push({
        id: `history-${index}`,
        role: "assistant",
        content: trimmed,
        created_at: parseIsoTimestamp(undefined, index),
      });
    }
  });
  return messages;
}

function parseStoredMessages(records: Array<Record<string, unknown>> | null | undefined): TimelineMessage[] {
  if (!records?.length) {
    return [];
  }
  return records
    .map((record, index) => {
      const role = safeRole(record["role"]);
      const content =
        typeof record["message"] === "string"
          ? (record["message"] as string)
          : typeof record["content"] === "string"
          ? (record["content"] as string)
          : "";
      if (!content) return null;
      return {
        id: `stored-${index}-${Math.abs(
          content.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0)
        )}`,
        role,
        content,
        created_at: parseIsoTimestamp(record["created_at"], index),
      };
    })
    .filter((value): value is TimelineMessage => value !== null);
}

function mergeMessages(historyMessages: TimelineMessage[], storedMessages: TimelineMessage[]): TimelineMessage[] {
  if (!historyMessages.length && !storedMessages.length) {
    return [];
  }
  const combined: TimelineMessage[] = [];
  const seen = new Set<string>();
  [...historyMessages, ...storedMessages]
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    .forEach((message) => {
      const key = `${message.role}|${message.created_at}|${message.content}`;
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      combined.push(message);
    });
  return combined;
}

export function RunChatPanel({ requestId, history, storedMessages, className }: RunChatPanelProps) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [pendingMessages, setPendingMessages] = useState<TimelineMessage[]>([]);
  const [baseSignature, setBaseSignature] = useState<string>("");

  const baseMessages = useMemo(() => {
    const historyMessages = parseHistory(history);
    const stored = parseStoredMessages(storedMessages);
    return mergeMessages(historyMessages, stored);
  }, [history, storedMessages]);

  const currentSignature = useMemo(() => {
    if (baseMessages.length === 0) {
      return "";
    }
    return baseMessages
      .map((message) => `${message.role}|${message.created_at}|${message.content}`)
      .join("||");
  }, [baseMessages]);

  useEffect(() => {
    if (currentSignature && currentSignature !== baseSignature) {
      setPendingMessages((current) =>
        current.filter((message) => {
          const existsInBase = baseMessages.some(
            (base) =>
              base.content === message.content &&
              base.role === message.role &&
              base.created_at === message.created_at
          );
          return !existsInBase;
        })
      );
      setBaseSignature(currentSignature);
    }
  }, [currentSignature, baseSignature, baseMessages]);

  const sendMutation = useMutation({
    mutationFn: sendChatMessage,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["request-detail", requestId] });
    },
    onError: (_error, _variables, context) => {
      if (context && typeof context.optimisticId === "string") {
        setPendingMessages((current) => current.filter((message) => message.id !== context.optimisticId));
      }
    },
  });

  const conversation = useMemo(
    () => [...baseMessages, ...pendingMessages],
    [baseMessages, pendingMessages]
  );

  const handleSend = (message: string) => {
    const trimmed = message.trim();
    if (!trimmed) {
      return;
    }
    const timestamp = new Date().toISOString();
    const id = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}`;
    const optimistic: TimelineMessage = {
      id,
      role: "user",
      content: trimmed,
      created_at: timestamp,
    };
    setPendingMessages((current) => [...current, optimistic]);
    sendMutation.mutate(
      { requestId, message: trimmed },
      {
        context: { optimisticId: id },
      }
    );
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
            <ChatTimeline messages={conversation} />
          </div>
        </div>
        <ChatComposer
          onSend={handleSend}
          placeholder="Ask Codex to keep going…"
          value={draft}
          onChange={setDraft}
          disabled={sendMutation.isPending}
        />
      </CardContent>
    </Card>
  );
}
