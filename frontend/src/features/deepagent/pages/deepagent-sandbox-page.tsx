import { useEffect, useMemo, useRef, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  const [preview, setPreview] = useState<
    | { kind: "none" }
    | { kind: "image"; name: string; url: string; downloadUrl: string }
    | { kind: "text"; name: string; content: string; downloadUrl: string }
    | { kind: "html"; name: string; url: string; downloadUrl: string }
  >({ kind: "none" });
  const previewObjectUrlRef = useRef<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const messageIdRef = useRef(0);
  const toolMessageIdsRef = useRef(new Map<string, string>());
  const fullOutputMapRef = useRef(new Map<string, string>());
  const [outputModal, setOutputModal] = useState<{ title: string; content: string } | null>(
    null
  );
  const toolStateRef = useRef(
    new Map<
      string,
      {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        arguments?: any;
        output?: string | null;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        artifacts?: any;
      }
    >()
  );

  const rewriteSandboxLinks = (content: string): string => {
    if (!conversation) return content;
    if (!content.includes("sandbox:")) return content;
    const sessionId = conversation.sandbox_session_id;
    const sandboxLinkPattern = /\[([^\]]+)\]\(sandbox:([^)]+)\)/g;
    return content.replace(sandboxLinkPattern, (match, label, rawPath) => {
      try {
        let path = String(rawPath || "").trim();
        if (!path) return match;
        if (path.startsWith("/workspace/")) {
          // already absolute
        } else if (path.startsWith("workspace/")) {
          path = `/workspace/${path.slice("workspace/".length)}`;
        } else if (!path.startsWith("/")) {
          path = `/workspace/${path}`;
        }
        const encodedPath = encodeURIComponent(path).replace(/%2F/g, "/");
        const filename = String(label || path.split("/").pop() || "download");
        const encodedFilename = encodeURIComponent(filename);
        const url = `/api/sandbox/sessions/${sessionId}/files/content?path=${encodedPath}&filename=${encodedFilename}&download=1`;
        return `[${filename}](${url})`;
      } catch {
        return match;
      }
    });
  };

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

  const formatToolMessageContent = (
    name: string,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    args: any | undefined,
    output: string | null | undefined,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    artifacts: any | undefined
  ): string => {
    const sections: string[] = [`**Tool:** \`${name}\``];

    if (args !== undefined && args !== null) {
      let json = "";
      try {
        json = JSON.stringify(args, null, 2);
      } catch {
        json = String(args);
      }
      sections.push(`**Arguments:**\n\n\`\`\`json\n${json}\n\`\`\``);
    }

    if (typeof output === "string" && output.trim().length > 0) {
      sections.push(`**Output:**\n\n\`\`\`\n${output}\n\`\`\``);
    }

    if (artifacts) {
      let lines: string[] = [];
      if (Array.isArray(artifacts)) {
        lines = artifacts.map((artifact, index) => {
          if (artifact && typeof artifact === "object") {
            const rawUrl =
              artifact.download_url ??
              artifact.url ??
              artifact.path ??
              artifact.storage_path ??
              "";
            const url =
              rawUrl && typeof rawUrl === "string"
                ? `${rawUrl}${rawUrl.includes("?") ? "&" : "?"}download=1`
                : "";
            const label = (artifact.filename ?? artifact.name ?? url) || `Artifact ${index + 1}`;
            if (url && typeof url === "string") {
              return `- [${label}](${url})`;
            }
            return `- ${label}`;
          }
          if (typeof artifact === "string") {
            const isUrl = /^https?:\/\//.test(artifact);
            if (isUrl) {
              return `- [Artifact ${index + 1}](${artifact})`;
            }
            return `- ${artifact}`;
          }
          return `- Artifact ${index + 1}`;
        });
      } else if (typeof artifacts === "object") {
        const rawUrl =
          artifacts.download_url ??
          artifacts.url ??
          artifacts.path ??
          artifacts.storage_path ??
          "";
        const url =
          rawUrl && typeof rawUrl === "string"
            ? `${rawUrl}${rawUrl.includes("?") ? "&" : "?"}download=1`
            : "";
        const label = (artifacts.filename ?? artifacts.name ?? url) || "Artifact";
        if (url && typeof url === "string") {
          lines = [`- [${label}](${url})`];
        } else {
          lines = [`- ${label}`];
        }
      } else if (typeof artifacts === "string") {
        const isUrl = /^https?:\/\//.test(artifacts);
        if (isUrl) {
          const url = `${artifacts}${artifacts.includes("?") ? "&" : "?"}download=1`;
          lines = [`- [Artifact](${url})`];
        } else {
          lines = [`- ${artifacts}`];
        }
      }

      if (lines.length > 0) {
        sections.push(`**Artifacts:**\n${lines.join("\n")}`);
      }
    }

    return rewriteSandboxLinks(sections.join("\n\n"));
  };

  const handleChunk = (chunk: DeepAgentChunk) => {
    // Error handling stays first so we surface failures clearly.
    const errorText = typeof chunk.error === "string" ? chunk.error : null;
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

    const updateToolMessage = (
      callKey: string,
      name: string,
      updates: { args?: unknown; output?: string | null; artifacts?: unknown }
    ) => {
      const currentState = toolStateRef.current.get(callKey) ?? {};
      if (updates.args !== undefined) {
        currentState.arguments = updates.args;
      }
      if (updates.output !== undefined) {
        currentState.output = updates.output;
        if (typeof updates.output === "string") {
          fullOutputMapRef.current.set(callKey, updates.output);
        }
      }
      if (updates.artifacts !== undefined) {
        currentState.artifacts = updates.artifacts;
      }
      toolStateRef.current.set(callKey, currentState);

      const outputText =
        typeof currentState.output === "string"
          ? currentState.output
          : fullOutputMapRef.current.get(callKey) ?? null;

      const content = formatToolMessageContent(
        name,
        currentState.arguments,
        outputText,
        currentState.artifacts
      );
      if (!content) return;

      const now = new Date().toISOString();
      setMessages((prev) => {
        const next = [...prev];
        const existingId = toolMessageIdsRef.current.get(callKey);
        if (existingId) {
          const index = next.findIndex((m) => m.id === existingId);
          if (index !== -1) {
            next[index] = {
              ...next[index],
              role: "tool",
              content
            };
            return next;
          }
        }

        messageIdRef.current += 1;
        const id = String(messageIdRef.current);
        toolMessageIdsRef.current.set(callKey, id);
        next.push({
          id,
          role: "tool",
          content,
          created_at: now
        });
        return next;
      });
    };

    const event = chunk.event;

    if (event === "tool_start" && chunk.data) {
      const name = chunk.data.tool_name ?? "tool";
      const callKey = chunk.data.tool_call_id ?? `name:${name}`;
      updateToolMessage(callKey, name, { args: chunk.data.args });
      return;
    }

    if (event === "tool_result" && chunk.data) {
      const name = chunk.data.tool_name ?? "tool";
      const callKey = chunk.data.tool_call_id ?? `name:${name}`;
      updateToolMessage(callKey, name, {
        output: typeof chunk.data.output === "string" ? chunk.data.output : null,
        artifacts: chunk.data.artifacts
      });
      return;
    }

    if (event === "tool_artifact" && chunk.data) {
      const name = chunk.data.tool_name ?? "tool";
      const callKey = chunk.data.tool_call_id ?? `name:${name}`;
      const current = toolStateRef.current.get(callKey) ?? {};
      const artifacts = current.artifacts;
      let nextArtifacts: unknown;
      if (Array.isArray(artifacts)) {
        nextArtifacts = [...artifacts, chunk.data.artifact];
      } else if (artifacts) {
        nextArtifacts = [artifacts, chunk.data.artifact];
      } else {
        nextArtifacts = [chunk.data.artifact];
      }
      updateToolMessage(callKey, name, { artifacts: nextArtifacts });
      return;
    }

    if (event === "delta" && chunk.data) {
      const msg = chunk.data as Record<string, unknown>;
      const msgData =
        (msg.data && typeof msg.data === "object" ? (msg.data as Record<string, unknown>) : {}) || {};
      const roleRaw = (msg.type ?? msg.role ?? msgData.role ?? "assistant") as string;
      const roleLower = String(roleRaw).toLowerCase();
      if (roleLower === "human" || roleLower === "user" || roleLower === "tool" || roleLower === "system") {
        return;
      }
      const normRole =
        roleLower === "ai" || roleLower === "assistant" || roleLower === "model" ? "assistant" : roleLower;
      const contentValue = msgData.content ?? (msg as { content?: unknown }).content ?? "";
      let contentText = "";
      if (Array.isArray(contentValue)) {
        const parts: string[] = [];
        contentValue.forEach((part) => {
          if (
            part &&
            typeof part === "object" &&
            "text" in part &&
            typeof (part as { text: unknown }).text === "string"
          ) {
            parts.push((part as { text: string }).text);
          }
        });
        contentText = parts.join("");
      } else if (typeof contentValue === "string") {
        contentText = contentValue;
      } else {
        contentText = String(contentValue ?? "");
      }
      const cleaned = rewriteSandboxLinks(contentText);
      if (!cleaned.trim()) return;

      const now = new Date().toISOString();
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last && last.role === normRole) {
          next[next.length - 1] = {
            ...last,
            content: cleaned,
            created_at: last.created_at
          };
          return next;
        }
        messageIdRef.current += 1;
        next.push({
          id: String(messageIdRef.current),
          role: normRole,
          content: cleaned,
          created_at: now
        });
        return next;
      });
      return;
    }
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
    if (preview.kind !== "none") {
      return "";
    }
    if (!sandboxImageUrl) {
      return "No screenshot yet. Send a message and we will attempt to capture the sandbox.";
    }
    return "";
  }, [conversation, sandboxImageUrl, preview.kind]);

  const handleFileLinkClick = async (href: string, label: string) => {
    if (href.startsWith("modal:")) {
      const key = href.replace("modal:", "");
      const content = fullOutputMapRef.current.get(key);
      if (!content) return;
      setOutputModal({
        title: label || "Tool Output",
        content,
      });
      return;
    }

    if (!href) return;
    try {
      const response = await fetch(href);
      if (!response.ok) {
        throw new Error(`Failed to fetch file preview: ${response.status}`);
      }
      const blob = await response.blob();

      const filename = label || href.split("/").pop() || "file";
      const lower = filename.toLowerCase();
      const isImage =
        lower.endsWith(".png") ||
        lower.endsWith(".jpg") ||
        lower.endsWith(".jpeg") ||
        lower.endsWith(".gif") ||
        lower.endsWith(".webp") ||
        lower.endsWith(".svg");
      if (isImage) {
        if (previewObjectUrlRef.current) {
          URL.revokeObjectURL(previewObjectUrlRef.current);
          previewObjectUrlRef.current = null;
        }
        const objectUrl = URL.createObjectURL(blob);
        previewObjectUrlRef.current = objectUrl;
        setPreview({ kind: "image", name: filename, url: objectUrl, downloadUrl: href });
        return;
      }

      const contentType = response.headers.get("Content-Type") || "";
      const isHtml =
        contentType.toLowerCase().includes("text/html") ||
        lower.endsWith(".html") ||
        lower.endsWith(".htm");
      if (isHtml) {
        const text = await blob.text();
        if (previewObjectUrlRef.current) {
          URL.revokeObjectURL(previewObjectUrlRef.current);
          previewObjectUrlRef.current = null;
        }
        const htmlBlob = new Blob([text], { type: "text/html" });
        const objectUrl = URL.createObjectURL(htmlBlob);
        previewObjectUrlRef.current = objectUrl;
        setPreview({
          kind: "html",
          name: filename,
          url: objectUrl,
          downloadUrl: href
        });
        return;
      }

      const text = await blob.text();
      const maxChars = 8000;
      const truncated = text.length > maxChars ? `${text.slice(0, maxChars)}…` : text;
      setPreview({
        kind: "text",
        name: filename,
        content: truncated || "[empty file]",
        downloadUrl: href,
      });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unknown error while loading preview.";
      setPreview({
        kind: "text",
        name: label || "Preview",
        content: `Failed to load file preview.\n\n${message}`,
        downloadUrl: href,
      });
    }
  };

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
              <ChatTimeline messages={messages} onLinkClick={handleFileLinkClick} />
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
          <CardHeader className="flex items-center justify-between gap-2 border-b border-border/60">
            <CardTitle className="text-sm font-semibold">
              {preview.kind === "none" ? "Sandbox Preview" : `Preview: ${preview.name}`}
            </CardTitle>
            {(preview.kind === "image" || preview.kind === "text" || preview.kind === "html") && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  const downloadUrl = preview.downloadUrl;
                  if (!downloadUrl) return;
                  window.open(downloadUrl, "_blank");
                }}
              >
                Download file
              </Button>
            )}
          </CardHeader>
          <CardContent className="flex flex-1 flex-col p-4">
            {sandboxHint && (
              <p className="mb-3 text-xs text-muted-foreground">
                {sandboxHint}
              </p>
            )}
            <div className="relative flex flex-1 items-center justify-center overflow-hidden rounded-xl border border-dashed border-border/70 bg-muted/40">
              {preview.kind === "image" && (
                <img
                  src={preview.url}
                  alt={preview.name}
                  className="h-full w-full object-contain"
                />
              )}
              {preview.kind === "text" && (
                <pre className="h-full w-full overflow-auto bg-background/90 p-3 text-xs text-foreground">
                  {preview.content}
                </pre>
              )}
              {preview.kind === "html" && (
                <iframe
                  src={preview.url}
                  title={preview.name}
                  className="h-full w-full border-0 bg-background"
                  sandbox="allow-scripts"
                />
              )}
              {preview.kind === "none" &&
                (sandboxImageUrl ? (
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
                ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <Dialog
        open={!!outputModal}
        onOpenChange={(open) => {
          if (!open) setOutputModal(null);
        }}
      >
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>{outputModal?.title || "Tool Output"}</DialogTitle>
          </DialogHeader>
          <div className="max-h-[70vh] overflow-auto rounded-lg border border-border bg-muted/40 p-4 text-sm">
            <pre className="whitespace-pre-wrap break-words text-foreground">
              {outputModal?.content}
            </pre>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
