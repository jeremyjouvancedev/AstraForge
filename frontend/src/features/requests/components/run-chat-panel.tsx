import { useEffect, useMemo, useState } from "react";

import { ScrollArea } from "@/components/ui/scroll-area";
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
  seedMessage?: {
    id?: string;
    content: string;
    createdAt?: string;
    role?: TimelineRole;
  };
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

export function RunChatPanel({ requestId, history, storedMessages, className, seedMessage }: RunChatPanelProps) {
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
          const normalizedContent = (message.content || "").trim();
          const existsInBase = baseMessages.some(
            (base) =>
              base.role === message.role &&
              (base.content || "").trim() === normalizedContent
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

  const normalizedSeed = useMemo(() => {
    if (!seedMessage?.content?.trim()) return null;
    const createdAt = seedMessage.createdAt
      ? parseIsoTimestamp(seedMessage.createdAt, -1)
      : new Date().toISOString();
    return {
      id: seedMessage.id ?? "request-seed",
      role: seedMessage.role ?? "user",
      content: seedMessage.content.trim(),
      created_at: createdAt,
    } satisfies TimelineMessage;
  }, [seedMessage]);

  const displayedConversation = useMemo(() => {
    if (!normalizedSeed) return conversation;
    const alreadyIncluded = conversation.some(
      (msg) => msg.content === normalizedSeed.content && msg.role === normalizedSeed.role
    );
    if (alreadyIncluded) return conversation;
    return [normalizedSeed, ...conversation];
  }, [conversation, normalizedSeed]);

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
    <div className={cn("flex h-full min-h-[360px] w-full flex-col overflow-hidden bg-transparent", className)}>
      <div className="flex flex-1 flex-col gap-4">
        <ScrollArea className="flex-1 bg-transparent">
          <div className="space-y-4 px-2 pt-2">
            {displayedConversation.length === 0 ? (
              <p className="text-sm text-muted-foreground">Aucune conversation pour le moment.</p>
            ) : (
              <ChatTimeline messages={displayedConversation} />
            )}
          </div>
        </ScrollArea>
          <ChatComposer
            onSend={handleSend}
            value={draft}
            onChange={setDraft}
            disabled={sendMutation.isPending}
          />        
      </div>
    </div>
  );
}
