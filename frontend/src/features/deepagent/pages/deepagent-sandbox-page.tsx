import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { isAxiosError } from "axios";
import { AlertCircle, Plus } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogFooter,
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
import { toast } from "@/components/ui/sonner";
import { useSandboxSessions, sandboxSessionsQueryKey } from "@/features/sandbox/hooks/use-sandbox-sessions";
import { useStopSandboxSession } from "@/features/sandbox/hooks/use-stop-sandbox-session";
import { uploadSandboxFile } from "@/lib/api-client";
import { extractApiErrorMessage } from "@/lib/api-error";
import {
  LLMSelectionFields,
  LLMProvider,
  ReasoningEffort
} from "@/features/chat/components/llm-selection-fields";

export default function DeepAgentSandboxPage() {
  const [conversation, setConversation] = useState<DeepAgentConversation | null>(null);
  const [llmProvider, setLlmProvider] = useState<LLMProvider>("ollama");
  const [llmModel, setLlmModel] = useState("gpt-oss:20b");
  const [reasoningCheck, setReasoningCheck] = useState(true);
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>("high");
  const [messages, setMessages] = useState<DeepAgentMessage[]>([]);
  const [input, setInput] = useState("");
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadPath, setUploadPath] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const inputClassName =
    "rounded-xl border-white/10 bg-black/40 text-zinc-100 ring-1 ring-white/5 placeholder:text-zinc-500 focus-visible:border-indigo-400/60 focus-visible:ring-indigo-400/60 focus-visible:ring-offset-0";
  const uploadInputClassName = `${inputClassName} h-9 text-xs`;
  const panelClassName =
    "home-card home-ring-soft rounded-3xl border border-white/10 bg-black/30 text-zinc-100 shadow-2xl shadow-indigo-500/20 backdrop-blur";
  const [sandboxImageUrl, setSandboxImageUrl] = useState<string | null>(null);
  const [preview, setPreview] = useState<
    | { kind: "none" }
    | { kind: "image"; name: string; url: string; downloadUrl: string }
    | { kind: "text"; name: string; content: string; downloadUrl: string }
    | { kind: "html"; name: string; url: string; downloadUrl: string }
  >({ kind: "none" });
  const previewObjectUrlRef = useRef<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
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
  const [provisionError, setProvisionError] = useState<string | null>(null);
  const { data: sandboxSessions, isLoading: sandboxSessionsLoading } = useSandboxSessions();
  const queryClient = useQueryClient();
  const stopSandbox = useStopSandboxSession();
  const activeSessions = useMemo(
    () =>
      (sandboxSessions ?? []).filter((session) => {
        const status = (session.status || "").toLowerCase();
        return status === "ready" || status === "starting";
      }),
    [sandboxSessions]
  );
  const uploadTarget = useMemo<{ path: string; error: string | null }>(() => {
    if (!selectedFile) {
      return { path: "", error: null };
    }
    try {
      return {
        path: buildSandboxUploadPath(uploadPath, selectedFile.name),
        error: null
      };
    } catch (error) {
      return {
        path: "",
        error: error instanceof Error ? error.message : "Invalid upload path."
      };
    }
  }, [selectedFile, uploadPath]);

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
        const url = `/api/sandbox/sessions/${sessionId}/files/content/?path=${encodedPath}&filename=${encodedFilename}&download=1`;
        return `[${filename}](${url})`;
      } catch {
        return match;
      }
    });
  };

  const createConversation = useCreateConversation();
  const sendMessageMutation = useSendDeepAgentMessage(conversation?.conversation_id ?? "");

  const triggerConversation = useCallback(
    (options?: { silent?: boolean }) => {
      const metadata: Record<string, unknown> = {
        llm: {
          provider: llmProvider,
          model: llmModel || (llmProvider === "ollama" ? "gpt-oss:20b" : "gpt-4o"),
          ...(llmProvider === "ollama" ? { reasoning_effort: reasoningEffort, reasoning_check: reasoningCheck } : {})
        }
      };
      createConversation.mutate({ metadata }, {
        onSuccess: (conv) => {
          setProvisionError(null);
          setConversation(conv);
          void queryClient.invalidateQueries({ queryKey: sandboxSessionsQueryKey });
        },
        onError: (error) => {
          setProvisionError(error.message);
          if (!options?.silent) {
            toast.error("Sandbox unavailable", {
              description: error.message
            });
          }
        }
      });
    },
    [createConversation, llmProvider, llmModel, reasoningEffort, reasoningCheck, queryClient]
  );

  const handleRetrySandbox = useCallback(() => {
    createConversation.reset();
    triggerConversation();
  }, [createConversation, triggerConversation]);

  useEffect(() => {
    // Automatic provisioning disabled to allow user to choose options first.
  }, []);

  const handleStopSession = useCallback(
    (sessionId: string, options?: { resetConversation?: boolean }) => {
      stopSandbox.mutate(sessionId, {
        onSuccess: () => {
          toast.success("Sandbox stopping", {
            description: "The sandbox is terminating now. You can start a fresh session shortly."
          });
          if (options?.resetConversation) {
            setConversation(null);
            setMessages([]);
            setPreview({ kind: "none" });
            setSandboxImageUrl(null);
            createConversation.reset();
            triggerConversation({ silent: true });
          } else {
            triggerConversation({ silent: true });
          }
        },
        onError: (error) => {
          const description =
            error instanceof Error ? error.message : "The sandbox could not be stopped.";
          toast.error("Unable to stop sandbox", { description });
        }
      });
    },
    [createConversation, stopSandbox, triggerConversation]
  );

  const handleStopCurrentSandbox = useCallback(() => {
    if (!conversation || stopSandbox.isPending) return;
    handleStopSession(conversation.sandbox_session_id, { resetConversation: true });
  }, [conversation, handleStopSession, stopSandbox.isPending]);

  const handleFileSelection = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    setUploadPath(file?.name ?? "");
  }, []);

  const handleUploadFile = useCallback(async () => {
    if (!conversation || !selectedFile || isUploading) return;
    if (!uploadTarget.path) {
      toast.error("Upload path invalid", {
        description: uploadTarget.error ?? "Please choose a path inside /workspace."
      });
      return;
    }
    setIsUploading(true);
    try {
      const result = await uploadSandboxFile(
        conversation.sandbox_session_id,
        uploadTarget.path,
        selectedFile
      );
      if (result.exit_code !== 0) {
        const detail = result.stderr?.trim() || result.stdout?.trim() || "Sandbox upload failed.";
        throw new Error(detail);
      }
      toast.success("File uploaded", { description: uploadTarget.path });
      setSelectedFile(null);
      setUploadPath("");
      setIsUploadModalOpen(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (error) {
      const message = isAxiosError(error)
        ? extractApiErrorMessage(error.response?.data) ?? error.message
        : error instanceof Error
          ? error.message
          : "File upload failed.";
      toast.error("File upload failed", { description: message });
    } finally {
      setIsUploading(false);
    }
  }, [
    conversation,
    isUploading,
    selectedFile,
    uploadTarget.error,
    uploadTarget.path,
    setIsUploadModalOpen
  ]);

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

  const [activeTab, setActiveTab] = useState("preview");

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

    // Switch to preview tab when a file is clicked
    setActiveTab("preview");

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
    <div className="relative z-10 flex h-full w-full flex-col gap-6 px-4 py-6 sm:px-6 lg:px-10">
      <header className="space-y-2 px-1">
        <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-indigo-200/80">
          Deep Agent Sandbox
        </p>
        <h1 className="text-3xl font-semibold text-white">Sandbox Conversations</h1>
        <p className="max-w-3xl text-sm text-zinc-300">
          Talk to a deep agent on the left while previewing its sandbox environment on the right. We surface tool outputs, artifacts, and screenshots inline.
        </p>
      </header>

      {provisionError ? (
        <div className="rounded-3xl border border-amber-400/30 bg-amber-500/10 p-4 text-amber-50 shadow-lg shadow-amber-900/20 backdrop-blur">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-1 items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 flex-none text-amber-200" />
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.3em] text-amber-200/80">
                  Sandbox unavailable
                </p>
                <p className="text-sm text-amber-50/90">{provisionError}</p>
              </div>
            </div>
            <Button
              variant="outline"
              className="rounded-xl border-amber-200/40 text-amber-50 hover:border-amber-100 hover:text-amber-100"
              onClick={handleRetrySandbox}
              disabled={createConversation.isPending}
            >
              {createConversation.isPending ? "Retrying..." : "Try again"}
            </Button>
          </div>
          <div className="mt-4 rounded-2xl border border-amber-200/20 bg-black/20 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-amber-200/80">
              Active sandboxes
            </p>
            {sandboxSessionsLoading ? (
              <p className="mt-2 text-xs text-amber-100/70">Loading sessions…</p>
            ) : activeSessions.length > 0 ? (
              <div className="mt-2 space-y-2">
                {activeSessions.map((session) => (
                  <div
                    key={session.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-100/10 bg-white/5 px-3 py-2 text-sm"
                  >
                    <div>
                      <p className="font-medium text-white">
                        {session.mode.toUpperCase()} · {session.status}
                      </p>
                      <p className="text-[11px] uppercase tracking-[0.2em] text-amber-100/70">
                        Created {session.created_at ? new Date(session.created_at).toLocaleString() : "recently"}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="rounded-xl border border-amber-200/20 text-amber-100 hover:bg-amber-500/10"
                      onClick={() => handleStopSession(session.id)}
                      disabled={stopSandbox.isPending}
                    >
                      {stopSandbox.isPending ? "Stopping..." : "Stop"}
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-2 text-xs text-amber-100/70">
                No other running sandboxes were detected. If the issue persists, try refreshing the page.
              </p>
            )}
          </div>
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 gap-6 lg:grid-cols-2">
        <Card className={`${panelClassName} flex min-h-0 flex-1 flex-col`}>
          <CardHeader className="border-b border-white/10 pb-4">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="text-sm font-semibold text-white">
                {conversation ? "Conversation" : "Setup Session"}
              </CardTitle>
              {conversation ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="rounded-xl border-white/20 text-white hover:border-red-300/60 hover:text-red-50"
                  onClick={handleStopCurrentSandbox}
                  disabled={stopSandbox.isPending}
                >
                  {stopSandbox.isPending ? "Stopping..." : "Stop sandbox"}
                </Button>
              ) : null}
            </div>
          </CardHeader>
          <CardContent className="flex min-h-0 flex-1 flex-col gap-4 p-4">
            {!conversation ? (
              <div className="flex flex-1 flex-col items-center justify-center space-y-8 py-12">
                <div className="text-center space-y-2">
                  <h3 className="text-lg font-medium text-white">Configure your Sandbox</h3>
                  <p className="text-sm text-zinc-400">Choose your environment settings before starting the deep agent.</p>
                </div>

                <div className="w-full max-w-xl space-y-6 rounded-2xl border border-white/5 bg-white/5 p-6 backdrop-blur-sm">
                  <LLMSelectionFields
                    provider={llmProvider}
                    onProviderChange={(val) => setLlmProvider(val as LLMProvider)}
                    model={llmModel}
                    onModelChange={setLlmModel}
                    reasoningCheck={reasoningCheck}
                    onReasoningCheckChange={setReasoningCheck}
                    reasoningEffort={reasoningEffort}
                    onReasoningEffortChange={setReasoningEffort}
                    disabled={createConversation.isPending}
                    compact
                  />
                  <div className="pt-4">
                    <Button 
                      className="w-full rounded-xl py-6 text-base font-semibold"
                      variant="brand"
                      onClick={() => triggerConversation()}
                      disabled={createConversation.isPending}
                    >
                      {createConversation.isPending ? "Provisioning..." : "Start Session"}
                    </Button>
                  </div>
                </div>
              </div>
            ) : (
              <>
                <div className="flex-1 min-h-0 overflow-y-auto rounded-2xl border border-white/5 bg-gradient-to-b from-indigo-950/40 via-black/30 to-black/50 p-3 shadow-inner shadow-indigo-900/30">
                  <ChatTimeline messages={messages} onLinkClick={handleFileLinkClick} />
                </div>
                <form
                  className="flex flex-col gap-2 sm:flex-row sm:items-center"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void handleSend();
                  }}
                >
                  <div className="flex w-full items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      className="rounded-xl border-white/20 text-white hover:border-indigo-300/60 hover:text-indigo-50"
                      onClick={() => setIsUploadModalOpen(true)}
                      disabled={!conversation || isUploading}
                      aria-label="Open file upload"
                    >
                      <Plus className="h-4 w-4" />
                    </Button>
                    <Input
                      value={input}
                      onChange={(event) => setInput(event.target.value)}
                      placeholder="Ask the deep agent to inspect or modify files in the sandbox..."
                      disabled={!conversation || isStreaming}
                      className={`${inputClassName} flex-1`}
                    />
                  </div>
                  <Button
                    type="submit"
                    variant="brand"
                    className="rounded-xl px-6"
                    disabled={!conversation || isStreaming || !input.trim()}
                  >
                    {isStreaming ? "Streaming..." : "Send"}
                  </Button>
                </form>
              </>
            )}
          </CardContent>
        </Card>

        <Card className={`${panelClassName} flex min-h-0 flex-1 flex-col`}>
          <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col h-full">
            <CardHeader className="flex flex-row items-center justify-between gap-2 border-b border-white/10 pb-4">
              <div className="flex items-center gap-4">
                <CardTitle className="text-sm font-semibold text-white">
                  {preview.kind === "none" ? "File Preview" : `Preview: ${preview.name}`}
                </CardTitle>
              </div>
              {(activeTab === "preview" && (preview.kind === "image" || preview.kind === "text" || preview.kind === "html")) && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="rounded-xl border border-white/10 bg-white/5 text-zinc-100 hover:bg-indigo-500/20 h-7 text-xs"
                  onClick={() => {
                    const downloadUrl = preview.downloadUrl;
                    if (!downloadUrl) return;
                    window.open(downloadUrl, "_blank");
                  }}
                >
                  Download
                </Button>
              )}
            </CardHeader>
            <CardContent className="flex min-h-0 flex-1 flex-col p-4">
              {sandboxHint && activeTab === "preview" ? (
                <p className="mb-3 text-xs text-zinc-300">{sandboxHint}</p>
              ) : null}
              
              <TabsContent value="preview" className="flex-1 min-h-0 data-[state=active]:flex flex-col mt-0 h-full">
                <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-2xl border border-dashed border-white/10 bg-gradient-to-b from-indigo-950/50 via-black/50 to-black/60">
                  {preview.kind === "image" && (
                    <img
                      src={preview.url}
                      alt={preview.name}
                      className="h-full w-full object-contain shadow-lg shadow-indigo-900/30"
                    />
                  )}
                  {preview.kind === "text" && (
                    <pre className="h-full w-full overflow-auto rounded-xl bg-black/60 p-4 text-xs text-indigo-50">
                      {preview.content}
                    </pre>
                  )}
                  {preview.kind === "html" && (
                    <iframe
                      src={preview.url}
                      title={preview.name}
                      className="h-full w-full border-0 rounded-xl bg-black/60"
                      sandbox="allow-scripts"
                    />
                  )}
                  {preview.kind === "none" &&
                    (sandboxImageUrl ? (
                      <img
                        src={sandboxImageUrl}
                        alt="Sandbox preview"
                        className="h-full w-full object-contain opacity-90"
                      />
                    ) : (
                      <div className="flex flex-col items-center gap-2 text-xs text-zinc-300">
                        <span className="text-sm text-white">No file selected.</span>
                        <span className="text-[10px] uppercase tracking-[0.3em] text-indigo-200/80">
                          Click a file link in the chat to preview
                        </span>
                      </div>
                    ))}
                </div>
              </TabsContent>
            </CardContent>
          </Tabs>
        </Card>
      </div>

      <Dialog open={isUploadModalOpen} onOpenChange={setIsUploadModalOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Upload file to sandbox</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={handleFileSelection}
                disabled={!conversation || isUploading}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="rounded-xl border-white/20 text-white hover:border-indigo-300/60 hover:text-indigo-50"
                onClick={() => fileInputRef.current?.click()}
                disabled={!conversation || isUploading}
              >
                Choose file
              </Button>
              <span className="text-xs text-zinc-300">
                {selectedFile ? selectedFile.name : "No file selected"}
              </span>
            </div>
            <Input
              value={uploadPath}
              onChange={(event) => setUploadPath(event.target.value)}
              placeholder="Relative path in /workspace (optional)"
              disabled={!conversation || isUploading}
              className={uploadInputClassName}
            />
            {uploadTarget.error ? (
              <p className="text-[10px] text-rose-200">{uploadTarget.error}</p>
            ) : (
              <p className="text-[10px] text-zinc-400">
                {selectedFile && uploadTarget.path
                  ? `Uploads to ${uploadTarget.path}`
                  : "Uploads land in /workspace"}
              </p>
            )}
          </div>
          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsUploadModalOpen(false)}
            >
              Close
            </Button>
            <Button
              type="button"
              variant="brand"
              onClick={() => void handleUploadFile()}
              disabled={
                !conversation ||
                !selectedFile ||
                isUploading ||
                !uploadTarget.path ||
                !!uploadTarget.error
              }
            >
              {isUploading ? "Uploading..." : "Upload"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
