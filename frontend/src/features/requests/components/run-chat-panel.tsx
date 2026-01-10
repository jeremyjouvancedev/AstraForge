import { useEffect, useMemo, useState } from "react";

import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatComposer } from "@/features/chat/components/chat-composer";
import { ChatTimeline } from "@/features/chat/components/chat-timeline";
import { cn } from "@/lib/cn";
import { sendChatMessage, Attachment } from "@/lib/api-client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ImageUpload } from "@/components/image-upload";

interface RunChatPanelProps {
  requestId: string;
  history?: string | null;
  storedMessages?: Array<Record<string, unknown>> | null;
  className?: string;
  latestAssistantMessage?: {
    id?: string;
    content: string;
    createdAt?: string;
  } | null;
  liveAssistantMessage?: {
    id?: string;
    content: string;
    createdAt?: string;
  } | null;
  seedMessage?: {
    id?: string;
    content: string;
    createdAt?: string;
    role?: TimelineRole;
    attachments?: Attachment[];
  };
}

type TimelineRole = "user" | "assistant" | "system";

interface TimelineMessage {
  id: string;
  role: TimelineRole;
  content: string;
  created_at: string;
  attachments?: Attachment[];
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
      const attachments = record.attachments as Attachment[] | undefined;
      const content =
        typeof record.content === "string"
          ? record.content
          : typeof record.message === "string"
          ? record.message
          : attachments && attachments.length > 0
          ? ""
          : "";

      // Allow empty content if there are attachments
      if (!content && (!attachments || attachments.length === 0)) return;

      const createdAt = parseIsoTimestamp(record.created_at ?? record.timestamp, index);
      const identifier = String(record.id ?? `history-${index}`);
      messages.push({
        id: identifier,
        role,
        content: content || (attachments && attachments.length > 0 ? "[Image]" : ""),
        created_at: createdAt,
        attachments,
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

function parseStoredMessages(
  records: Array<Record<string, unknown>> | null | undefined
): TimelineMessage[] {
  if (!records?.length) {
    return [];
  }
  const results: (TimelineMessage | null)[] = records.map((record, index) => {
    const role = safeRole(record["role"]);
    const attachments = record["attachments"] as Attachment[] | undefined;
    const content =
      typeof record["message"] === "string"
        ? (record["message"] as string)
        : typeof record["content"] === "string"
        ? (record["content"] as string)
        : "";

    // Allow empty content if there are attachments
    if (!content && (!attachments || attachments.length === 0)) return null;

    return {
      id: `stored-${index}-${Math.abs(
        (content || "no-content").split("").reduce((acc, char) => acc + char.charCodeAt(0), 0)
      )}`,
      role,
      content: content || (attachments && attachments.length > 0 ? "[Image]" : ""),
      created_at: parseIsoTimestamp(record["created_at"], index),
      attachments,
    };
  });

  return results.filter((value): value is TimelineMessage => value !== null);
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
      const attKey = (message.attachments || []).map(a => a.name).join(",");
      // Use id as part of the key to distinguish optimistic messages from stored ones if content is identical
      const key = `${message.id}|${message.role}|${message.created_at}|${message.content}|${attKey}`;
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      combined.push(message);
    });
  return combined;
}

export function RunChatPanel({
  requestId,
  history,
  storedMessages,
  className,
  seedMessage,
  latestAssistantMessage,
  liveAssistantMessage,
}: RunChatPanelProps) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [images, setImages] = useState<Attachment[]>([]);
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
      .map((message) => {
        const attKey = (message.attachments || []).map((a) => a.name).join(",");
        return `${message.role}|${message.created_at}|${message.content}|${attKey}`;
      })
      .join("||");
  }, [baseMessages]);

  useEffect(() => {
    if (currentSignature && currentSignature !== baseSignature) {
      setPendingMessages((current) =>
        current.filter((message) => {
          const normalizedContent = (message.content || "").trim();
          const attKey = (message.attachments || []).map((a) => a.name).join(",");
          const existsInBase = baseMessages.some((base) => {
            const baseAttKey = (base.attachments || []).map((a) => a.name).join(",");
            return (
              base.role === message.role &&
              (base.content || "").trim() === normalizedContent &&
              baseAttKey === attKey
            );
          });
          return !existsInBase;
        })
      );
      setBaseSignature(currentSignature);
    }
  }, [currentSignature, baseSignature, baseMessages]);

  const sendMutation = useMutation<
    { status: string },
    Error,
    {
      requestId: string;
      message: string;
      attachments?: Attachment[];
    }
  >({
    mutationFn: sendChatMessage,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["request-detail", requestId] });
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
      attachments: seedMessage.attachments,
    } satisfies TimelineMessage;
  }, [seedMessage]);

  const conversationWithSeed = useMemo(() => {
    if (!normalizedSeed) return conversation;
    const alreadyIncluded = conversation.some(
      (msg) => msg.content === normalizedSeed.content && msg.role === normalizedSeed.role
    );
    if (alreadyIncluded) return conversation;
    return [normalizedSeed, ...conversation];
  }, [conversation, normalizedSeed]);

  const assistantCandidate = liveAssistantMessage ?? latestAssistantMessage;

  const assistantFromRun = useMemo(() => {
    const content = assistantCandidate?.content?.trim();
    if (!content) return null;
    const createdAt = assistantCandidate?.createdAt
      ? parseIsoTimestamp(assistantCandidate.createdAt, -2)
      : new Date().toISOString();
    const hash = Math.abs(content.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0));
    return {
      id: assistantCandidate?.id ?? `run-assistant-${hash}`,
      role: "assistant" as TimelineRole,
      content,
      created_at: createdAt,
    } satisfies TimelineMessage;
  }, [assistantCandidate]);

  const displayedConversation = useMemo(() => {
    if (!assistantFromRun) return conversationWithSeed;
    const alreadyIncluded = conversationWithSeed.some(
      (msg) => msg.role === "assistant" && msg.content.trim() === assistantFromRun.content.trim()
    );
    if (alreadyIncluded) return conversationWithSeed;
    return [...conversationWithSeed, assistantFromRun];
  }, [conversationWithSeed, assistantFromRun]);

  const handleSend = (message: string) => {
    const trimmed = message.trim();
    if (!trimmed && images.length === 0) {
      return;
    }
    const timestamp = new Date().toISOString();
    const id =
      typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}`;
    const optimistic: TimelineMessage = {
      id,
      role: "user",
      content: trimmed || (images.length > 0 ? "[Image attached]" : ""),
      created_at: timestamp,
      attachments: images.length > 0 ? [...images] : undefined,
    };
    setPendingMessages((current) => [...current, optimistic]);
    sendMutation.mutate(
      {
        requestId,
        message: trimmed,
        attachments: images.length > 0 ? images : undefined,
      },
      {
        onError: () => {
          setPendingMessages((current) => current.filter((message) => message.id !== id));
        },
        onSuccess: () => {
          setImages([]);
        },
      }
    );
    setDraft("");
  };

  return (
    <div
      className={cn(
        "flex h-full min-h-[360px] w-full flex-col overflow-hidden bg-transparent",
        className
      )}
    >
      <div className="flex min-h-0 flex-1 flex-col gap-4">
        <ScrollArea className="min-h-0 flex-1 bg-transparent">
          <div className="space-y-4 px-2 pt-2">
            {displayedConversation.length === 0 ? (
              <p className="text-sm text-muted-foreground">Aucune conversation pour le moment.</p>
            ) : (
              <ChatTimeline messages={displayedConversation} />
            )}
          </div>
        </ScrollArea>
        <div className="flex flex-col gap-2 px-2">
          <ImageUpload images={images} setImages={setImages} disabled={sendMutation.isPending} />
          <ChatComposer
            onSend={handleSend}
            value={draft}
            onChange={setDraft}
            disabled={sendMutation.isPending}
            showContextButton={false}
            showMicrophoneButton={false}
          />
        </div>
      </div>
    </div>
  );
}
