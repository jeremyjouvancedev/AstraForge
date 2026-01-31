import React, { useState, useEffect, useMemo, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import type { Components } from "react-markdown";
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle, 
  DialogFooter,
  DialogDescription
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import {
  uploadSandboxFile,
  readSandboxFile,
  uploadAstraControlDocument,
} from '@/lib/api-client';
import { buildSandboxUploadPath } from '@/features/deepagent/lib/sandbox-upload';
import { useAstraControl } from '../hooks/useAstraControl';
import { LLMSelectionFields, LLMProvider, ReasoningEffort } from '@/features/chat/components/llm-selection-fields';
import { type AstraControlSession, type PlanStep, type AgentPayload, type InterruptPayload, type AgentMessage, type HumanInputPayload } from '../types';
import { cn } from '@/lib/utils';
import { 
  Plus, 
  Sparkles,
  Terminal, 
  CheckCircle2, 
  AlertCircle, 
  Play, 
  History, 
  Settings2,
  Clock,
  ListTodo,
  Circle,
  Code2,
  Globe,
  Box,
  Upload,
  Paperclip,
  Search,
  Zap,
  BarChart3,
  Layers,
  MessageSquare,
  Bot,
  User,
  ChevronRight,
  ChevronDown,
  Activity,
  ShieldCheck,
  Square,
  Eye,
  FileText,
  Download
} from 'lucide-react';

function summarizeSessions(sessions: AstraControlSession[]) {
  let running = 0;
  let completed = 0;
  let failed = 0;
  sessions.forEach((s) => {
    if (s.status === 'running') running += 1;
    if (s.status === 'completed') completed += 1;
    if (s.status === 'failed') failed += 1;
  });
  return { total: sessions.length, running, completed, failed };
}

function getErrorMessage(error: unknown, defaultMessage: string): string {
  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as { response?: { data?: { error?: string } } }).response;
    return response?.data?.error || defaultMessage;
  }
  return defaultMessage;
}

const CAPABILITY_EXAMPLES = [
  {
    title: "Autonomous Research",
    goal: "Conduct a market analysis of current AI agent frameworks. Compare LangGraph, CrewAI, and AutoGPT. Generate a detailed markdown report comparing their architecture, strengths, and business use cases.",
    icon: Search,
    color: "text-blue-400"
  },
  {
    title: "Website/App Creation",
    goal: "Design and implement a modern React landing page using Tailwind CSS. Create the project structure, develop responsive components, and ensure the code is optimized for production deployment.",
    icon: Globe,
    color: "text-emerald-400"
  },
  {
    title: "Data Analysis & Insights",
    goal: "Analyze the sales data CSV in the workspace. Calculate growth trends, perform customer segmentation using python, and deliver a concise executive summary with actionable business insights.",
    icon: BarChart3,
    color: "text-purple-400"
  },
  {
    title: "Autonomous Developer",
    goal: "Audit the local repository code for security vulnerabilities and performance bottlenecks. Refactor identified issues, implement unit tests, and verify the fixes through automated execution.",
    icon: Code2,
    color: "text-amber-400"
  },
  {
    title: "Workflow Automation",
    goal: "Automate a multi-step business process: monitor a specific directory for new documents, summarize their content, and format the findings into a professional PDF internal report.",
    icon: Zap,
    color: "text-rose-400"
  },
  {
    title: "End-to-End Projects",
    goal: "Plan and execute a complete migration of the project's documentation to a structured Docusaurus site. Handle initialization, content conversion, and custom theme configuration autonomously.",
    icon: Layers,
    color: "text-indigo-400"
  }
];

const markdownComponents: Components = {
  h1: ({ className, ...props }) => (
    <h1
      {...props}
      className={cn(
        "mt-4 border-b border-white/10 pb-1 text-xl font-semibold text-white",
        className
      )}
    />
  ),
  h2: ({ className, ...props }) => (
    <h2
      {...props}
      className={cn(
        "mt-4 border-b border-white/5 pb-1 text-lg font-semibold text-white",
        className
      )}
    />
  ),
  h3: ({ className, ...props }) => (
    <h3
      {...props}
      className={cn("mt-3 text-base font-semibold text-zinc-100", className)}
    />
  ),
  h4: ({ className, ...props }) => (
    <h4
      {...props}
      className={cn("mt-3 text-sm font-semibold text-zinc-200", className)}
    />
  ),
  p: ({ ...props }) => (
    <p
      {...props}
      className={cn("my-3 leading-relaxed text-zinc-300", props.className)}
    />
  ),
  strong: ({ ...props }) => (
    <strong {...props} className={cn("font-semibold text-white", props.className)} />
  ),
  em: ({ ...props }) => (
    <em {...props} className={cn("text-zinc-200/80", props.className)} />
  ),
  blockquote: ({ ...props }) => (
    <blockquote
      {...props}
      className={cn(
        "my-4 border-l-4 border-blue-500/50 bg-white/5 px-4 py-2 text-sm italic text-zinc-400",
        props.className
      )}
    />
  ),
  ul: ({ ...props }) => (
    <ul
      {...props}
      className={cn("my-3 list-disc space-y-1 pl-5 text-zinc-300", props.className)}
    />
  ),
  ol: ({ ...props }) => (
    <ol
      {...props}
      className={cn("my-3 list-decimal space-y-1 pl-5 text-zinc-300", props.className)}
    />
  ),
  li: ({ ...props }) => (
    <li {...props} className={cn("leading-relaxed", props.className)} />
  ),
  code: ({
    children,
    inline,
    className,
    ...props
  }: {
    children?: React.ReactNode;
    inline?: boolean;
    className?: string;
  }) => {
    if (inline) {
      return (
        <code
          {...props}
          className={cn(
            "inline-flex items-center gap-1 rounded-md border border-white/10 bg-white/5 px-1.5 py-0.5 text-[0.92em] font-mono text-blue-300",
            className
          )}
        >
          <span>{children}</span>
        </code>
      );
    }
    return (
      <code {...props} className={cn("font-mono text-xs leading-relaxed", className)}>
        {children}
      </code>
    );
  },
  pre: ({ className, children, ...props }) => (
    <pre
      {...props}
      className={cn(
        "my-3 overflow-x-hidden overflow-y-auto rounded-xl border border-white/10 bg-black/40 px-0 py-0 text-sm text-zinc-200",
        className
      )}
    >
      <code className="block whitespace-pre-wrap break-words px-4 py-3 font-mono text-xs leading-relaxed text-zinc-300">
        {children}
      </code>
    </pre>
  ),
  table: ({ ...props }) => (
    <div className="my-4 overflow-hidden rounded-xl border border-white/10">
      <table {...props} className="w-full text-left text-sm text-zinc-300" />
    </div>
  ),
  thead: ({ ...props }) => (
    <thead {...props} className={cn("bg-white/5 text-white", props.className)} />
  ),
  th: ({ ...props }) => (
    <th
      {...props}
      className={cn("border-b border-white/10 px-3 py-2 text-xs font-semibold", props.className)}
    />
  ),
  td: ({ ...props }) => (
    <td
      {...props}
      className={cn("border-b border-white/5 px-3 py-2 text-xs", props.className)}
    />
  ),
  a: ({ ...props }) => {
    return (
      <a
        {...props}
        target="_blank"
        rel="noreferrer"
        className={cn(
          "text-blue-400 underline underline-offset-2 transition hover:text-blue-300",
          props.className
        )}
      >
        {props.children}
      </a>
    );
  },
};

export function AstraControlPage() {
  const [view, setView] = useState<'setup' | 'live'>('setup');
  const [goal, setGoal] = useState('');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<AstraControlSession[]>([]);
  const [llmProvider, setLlmProvider] = useState<LLMProvider>('ollama');
  const [llmModel, setLlmModel] = useState('devstral-small-2:24b');
  const [reasoningCheck, setReasoningCheck] = useState(false);
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>('high');
  const [validationRequired, setValidationRequired] = useState(true);

  const [isResuming, setIsResuming] = useState(false);
  const [isDebugOpen, setIsDebugOpen] = useState(false);
  const [messageInput, setMessageInput] = useState("");
  const [isSendingMessage, setIsSendingMessage] = useState(false);

  const scrollRef = React.useRef<HTMLDivElement>(null);

  // File upload state
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadPath, setUploadPath] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  // File preview state
  const [previewFilePath, setPreviewFilePath] = useState<string | null>(null);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  // Document upload state
  const [isDocUploadModalOpen, setIsDocUploadModalOpen] = useState(false);
  const [uploadingDoc, setUploadingDoc] = useState(false);
  const [docFiles, setDocFiles] = useState<File[]>([]);
  const [docDescriptions, setDocDescriptions] = useState<Record<string, string>>({});

  const { events, status, startSession, resumeSession, cancelSession, sendMessage, fetchSessions } = useAstraControl(sessionId);

  useEffect(() => {
    if (view === 'live') {
      scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [events, view]);

  const conversation = useMemo(() => {
    // We want a unified timeline: Goal -> Tool Proposals -> Results -> Agent Commentary -> Human Input
    return events.filter(e => {
      if (e.type === 'agent') {
        const payload = e.payload as AgentPayload;
        const messages = payload.messages || [];
        // Show agent if it has text OR if it's proposing tool calls
        return messages.some((m: AgentMessage) => 
          (m.role === 'assistant' && m.content) || 
          (m.role === 'assistant' && m.tool_calls && m.tool_calls.length > 0)
        );
      }
      if (e.type === 'tools') return true; // Show results of tool execution
      if (e.type === 'interrupt' && (e.payload as InterruptPayload).action === 'wait_for_user') return true;
      if (e.type === 'human_input') return true;
      if (e.type === 'agent' && (e.payload as AgentPayload).is_finished) return true;
      return false;
    });
  }, [events]);

  const activeSession = useMemo(() => {
    return sessions.find(s => s.id === sessionId) || null;
  }, [sessions, sessionId]);

  const fileTree = useMemo(() => {
    const observerEvents = events.filter(e => e.type === 'observer');
    if (observerEvents.length === 0) return [];
    const latestObserver = observerEvents[observerEvents.length - 1];
    return ((latestObserver.payload as AgentPayload).file_tree || []) as string[];
  }, [events]);

  const uploadTarget = useMemo<{ path: string; error: string | null }>(() => {
    if (!selectedFile) return { path: "", error: null };
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

  const handleUploadFile = useCallback(async () => {
    if (!activeSession?.sandbox_session || !selectedFile || isUploading) return;
    if (!uploadTarget.path) {
      toast.error("Upload path invalid", {
        description: uploadTarget.error ?? "Please choose a path inside /workspace."
      });
      return;
    }

    setIsUploading(true);
    try {
      const result = await uploadSandboxFile(
        activeSession.sandbox_session,
        uploadTarget.path,
        selectedFile
      );

      if (result.exit_code === 0) {
        toast.success("File uploaded", { description: uploadTarget.path });
        setUploadPath("");
        setSelectedFile(null);
        setIsUploadModalOpen(false);
      } else {
        const detail = result.stderr?.trim() || result.stdout?.trim() || "Sandbox upload failed.";
        toast.error("Upload failed", { description: detail });
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "File upload failed.";
      toast.error("File upload failed", { description: message });
    } finally {
      setIsUploading(false);
    }
  }, [activeSession, selectedFile, isUploading, uploadTarget]);

  const loadSessions = useCallback(async () => {
    try {
      const data = await fetchSessions();
      setSessions(data);
    } catch (err) {
      console.error("Failed to load sessions:", err);
    }
  }, [fetchSessions]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions, sessionId]);

  const summary = useMemo(() => summarizeSessions(sessions), [sessions]);

  const { planSteps, rawPlan } = useMemo(() => {
    const plannerEvents = events.filter(e => e.type === 'planner');
    if (plannerEvents.length === 0) return { planSteps: [], rawPlan: '' };
    const latestPlanner = plannerEvents[plannerEvents.length - 1];
    const payload = latestPlanner.payload as AgentPayload;
    return {
      planSteps: (payload.plan_steps || []) as PlanStep[],
      rawPlan: payload.plan || ''
    };
  }, [events]);

  const latestInterrupt = useMemo(() => {
    const interruptEvents = events.filter(e => e.type === 'interrupt');
    if (interruptEvents.length === 0) return null;
    return interruptEvents[interruptEvents.length - 1].payload as InterruptPayload;
  }, [events]);

  const handleStart = async () => {
    if (!goal) return;
    try {
      const session = await startSession(
        goal,
        llmModel,
        llmProvider,
        reasoningCheck,
        reasoningEffort,
        validationRequired
      );
      // Immediately add the new session to the list so it's available for find()
      setSessions(prev => [session, ...prev]);
      setSessionId(session.id);

      // Upload documents if any were selected
      if (docFiles.length > 0) {
        // Show a toast that documents will be uploaded once sandbox is ready
        toast.info(`Waiting for sandbox to start before uploading ${docFiles.length} document(s)...`);

        // Wait for sandbox to be ready with retries
        const maxRetries = 30; // 30 seconds max wait
        let retries = 0;
        let sandboxReady = false;

        while (retries < maxRetries && !sandboxReady) {
          try {
            // Fetch the latest session data to check sandbox status
            const sessions = await fetchSessions();
            const currentSession = sessions.find(s => s.id === session.id);

            if (currentSession?.sandbox_status === 'ready') {
              sandboxReady = true;
              break;
            } else if (currentSession?.sandbox_status === 'failed') {
              toast.error("Sandbox failed to start. Cannot upload documents.");
              break;
            }

            // Wait 1 second before next check
            await new Promise(resolve => setTimeout(resolve, 1000));
            retries++;
          } catch (err) {
            console.error("Failed to check sandbox status:", err);
            break;
          }
        }

        if (sandboxReady) {
          try {
            for (let i = 0; i < docFiles.length; i++) {
              const file = docFiles[i];
              const description = docDescriptions[i.toString()] || '';
              await uploadAstraControlDocument(session.id, file, description);
            }
            toast.success(`Uploaded ${docFiles.length} document(s)`);
            setDocFiles([]);
            setDocDescriptions({});
          } catch (uploadErr: unknown) {
            console.error("Failed to upload documents:", uploadErr);
            const errorMessage = getErrorMessage(uploadErr, "Failed to upload some documents");
            toast.error(errorMessage);
          }
        } else if (retries >= maxRetries) {
          toast.error("Timeout waiting for sandbox to start. You can upload documents manually once it's ready.");
        }
      }

      setView('live');
    } catch (err) {
      console.error("Failed to start agent session:", err);
      toast.error("Failed to start session");
    }
  };

  const handleResume = async () => {
    setIsResuming(true);
    try {
      await resumeSession();
    } catch (err) {
      console.error("Failed to resume session:", err);
    } finally {
      setIsResuming(false);
    }
  };

  const [planTab, setPlanTab] = useState<'checklist' | 'markdown'>('checklist');

  const handleCancel = async () => {
    try {
      await cancelSession();
      toast.success("Session cancellation requested");
    } catch (err) {
      console.error("Failed to cancel session:", err);
      toast.error("Failed to cancel session");
    }
  };

  const handleSendMessage = async () => {
    if (!messageInput.trim()) return;
    setIsSendingMessage(true);
    try {
      await sendMessage(messageInput, validationRequired);
      setMessageInput("");
    } catch (err) {
      console.error("Failed to send message:", err);
      toast.error("Failed to send message");
    } finally {
      setIsSendingMessage(false);
    }
  };

  const handleSelectSession = (id: string) => {
    setSessionId(id);
    setView('live');
  };

  const handlePreviewFile = async (path: string) => {
    if (!activeSession?.sandbox_session) return;
    setPreviewFilePath(path);
    setIsPreviewLoading(true);
    setPreviewContent(null);

    // Check if file is an image
    const isImage = /\.(png|jpg|jpeg|gif|webp|svg|bmp|ico)$/i.test(path);

    try {
      if (isImage) {
        // For images, we'll store a special marker and the actual image will be loaded via img src
        setPreviewContent("__IMAGE__");
      } else {
        const content = await readSandboxFile(activeSession.sandbox_session, path);
        setPreviewContent(content);
      }
    } catch (err) {
      console.error("Failed to read file:", err);
      toast.error("Failed to read file content");
      setPreviewFilePath(null);
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const handleAddDocFiles = (files: FileList | null) => {
    if (!files) return;
    const newFiles = Array.from(files);
    setDocFiles(prev => [...prev, ...newFiles]);
  };

  const handleRemoveDocFile = (index: number) => {
    setDocFiles(prev => prev.filter((_, i) => i !== index));
    setDocDescriptions(prev => {
      const newDescriptions = { ...prev };
      delete newDescriptions[index.toString()];
      return newDescriptions;
    });
  };

  const handleDocDescriptionChange = (index: number, description: string) => {
    setDocDescriptions(prev => ({ ...prev, [index.toString()]: description }));
  };

  const handleUploadDocuments = async () => {
    if (docFiles.length === 0) return;

    // If there's an active session, upload immediately
    if (activeSession?.id) {
      // Check if sandbox is ready
      if (activeSession.sandbox_status !== "ready") {
        toast.error(`Cannot upload documents. Sandbox status: ${activeSession.sandbox_status || 'unknown'}`);
        return;
      }

      setUploadingDoc(true);
      try {
        for (let i = 0; i < docFiles.length; i++) {
          const file = docFiles[i];
          const description = docDescriptions[i.toString()] || '';
          await uploadAstraControlDocument(activeSession.id, file, description);
        }
        toast.success(`Successfully uploaded ${docFiles.length} document(s)`);
        setDocFiles([]);
        setDocDescriptions({});
        setIsDocUploadModalOpen(false);
        // Refresh session data
        await fetchSessions();
      } catch (err: unknown) {
        console.error("Failed to upload documents:", err);
        const errorMessage = getErrorMessage(err, "Failed to upload documents");
        if (errorMessage.includes("Sandbox is not ready")) {
          toast.error("Sandbox is still starting. Please wait and try again.");
        } else {
          toast.error(errorMessage);
        }
      } finally {
        setUploadingDoc(false);
      }
    } else {
      // If no active session, just close the modal - documents are staged
      toast.success(`${docFiles.length} document(s) ready to upload`);
      setIsDocUploadModalOpen(false);
    }
  };


  return (
    <div className="relative z-10 mx-auto w-full max-w-[clamp(72rem,85vw,120rem)] space-y-8 px-4 py-8 text-zinc-100 sm:px-6 lg:px-10">
      {/* Header */}
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div className="space-y-2">
           <div className="flex items-center gap-2 text-blue-400 font-semibold uppercase tracking-[0.2em] text-[10px]">
             <Terminal className="h-3 w-3" />
             Astra Control
           </div>
           <h1 className="text-4xl font-bold text-white tracking-tight">System Control</h1>
           <p className="text-zinc-400 max-w-xl text-sm leading-relaxed">
             Execute complex system tasks across your Ubuntu environments with autonomous terminal agents.
           </p>
        </div>

        <div className="flex items-center gap-4 bg-black/40 border border-white/10 rounded-2xl p-1 shadow-xl">
           <Button 
            variant={view === "setup" ? "secondary" : "ghost"} 
            onClick={() => setView("setup")}
            className="rounded-xl h-10 px-6 font-medium transition-all"
           >
             <Plus className="h-4 w-4 mr-2" />
             New Task
           </Button>
           <Button 
            variant={view === "live" ? "secondary" : "ghost"} 
            onClick={() => setView("live")}
            disabled={!sessionId}
            className="rounded-xl h-10 px-6 font-medium transition-all"
           >
             Live Stream
           </Button>
        </div>
      </header>

      {view === 'setup' && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr,320px] gap-8 items-start animate-in fade-in slide-in-from-bottom-4 duration-500">
          <Card className="border-white/5 bg-zinc-900/50 backdrop-blur-md rounded-3xl overflow-hidden shadow-2xl">
            <CardHeader className="border-b border-white/5 bg-white/[0.02] p-6">
              <CardTitle className="text-xl flex items-center gap-2">
                <Play className="h-5 w-5 text-blue-500 fill-blue-500/20" />
                Initialize Environment Agent
              </CardTitle>
            </CardHeader>
            <CardContent className="p-8 space-y-10">
              <div className="space-y-6">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-blue-400" />
                  <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                    Capabilities & Examples
                  </label>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {CAPABILITY_EXAMPLES.map((example, idx) => (
                    <button
                      key={idx}
                      onClick={() => setGoal(example.goal)}
                      className="flex items-start gap-4 p-4 rounded-2xl bg-white/5 border border-white/5 hover:bg-white/10 hover:border-blue-500/30 transition-all text-left group"
                    >
                      <div className={cn("p-2 rounded-xl bg-black/40 border border-white/5 group-hover:scale-110 transition-transform", example.color)}>
                        <example.icon className="h-4 w-4" />
                      </div>
                      <div className="space-y-1">
                        <div className="text-xs font-bold text-zinc-200 group-hover:text-blue-400 transition-colors">{example.title}</div>
                        <p className="text-[10px] text-zinc-500 leading-tight line-clamp-2 italic">"{example.goal}"</p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-4">
                <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Execution Goal</label>
                <div className="flex space-x-3">
                  <Input
                    value={goal}
                    onChange={(e) => setGoal(e.target.value)}
                    placeholder="e.g. Install nodejs and create a hello world app"
                    className="h-12 bg-black/40 border-white/10 rounded-xl focus:ring-blue-500/50 transition-all"
                  />
                  <Button
                    onClick={handleStart}
                    disabled={!goal}
                    className="h-12 px-8 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold shadow-lg shadow-blue-900/20 transition-all"
                  >
                    Launch
                  </Button>
                </div>
              </div>

              <div className="pt-6 border-t border-white/5">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <Paperclip className="h-4 w-4 text-zinc-500" />
                    <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                      Documents (Optional)
                    </label>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setIsDocUploadModalOpen(true)}
                    className="h-8 px-4 rounded-lg text-xs"
                  >
                    <Upload className="h-3 w-3 mr-2" />
                    Add Documents
                  </Button>
                </div>
                {docFiles.length > 0 && (
                  <div className="space-y-2">
                    {docFiles.map((file, idx) => (
                      <div key={idx} className="flex items-center gap-2 p-3 rounded-lg bg-white/5 border border-white/5">
                        <FileText className="h-4 w-4 text-blue-400" />
                        <span className="text-sm text-zinc-300 flex-1">{file.name}</span>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRemoveDocFile(idx)}
                          className="h-6 w-6 p-0 hover:bg-red-500/20"
                        >
                          <span className="text-red-400">×</span>
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
                {docFiles.length === 0 && (
                  <p className="text-xs text-zinc-500 italic">
                    Upload documents (PDF, CSV, code files, etc.) to provide context for the agent.
                  </p>
                )}
              </div>

              <div className="pt-6 border-t border-white/5">
                <div className="flex items-center gap-2 mb-6">
                  <Settings2 className="h-4 w-4 text-zinc-500" />
                  <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                    Engine Configuration
                  </label>
                </div>
                <div className="p-6 bg-black/20 rounded-2xl border border-white/5">
                  <LLMSelectionFields
                    provider={llmProvider}
                    onProviderChange={(val) => setLlmProvider(val as LLMProvider)}
                    model={llmModel}
                    onModelChange={setLlmModel}
                    reasoningCheck={reasoningCheck}
                    onReasoningCheckChange={setReasoningCheck}
                    reasoningEffort={reasoningEffort}
                    onReasoningEffortChange={setReasoningEffort}
                  />

                  <div className="mt-8 pt-6 border-t border-white/5 space-y-4">
                    <div className="flex items-center justify-between p-4 bg-white/5 rounded-2xl border border-white/5 group hover:border-blue-500/30 transition-all">
                      <div className="space-y-1">
                        <Label htmlFor="validation-mode" className="text-sm font-bold text-zinc-200">
                          {validationRequired ? "Validated Execution" : "Full Automatic"}
                        </Label>
                        <p className="text-[10px] text-zinc-500 leading-relaxed max-w-[240px]">
                          {validationRequired 
                            ? "Agent will pause and ask for your approval before every terminal command or file change." 
                            : "Agent will execute all actions autonomously without waiting for your validation."}
                        </p>
                      </div>
                      <Switch 
                        id="validation-mode"
                        checked={validationRequired}
                        onCheckedChange={setValidationRequired}
                        className="data-[state=checked]:bg-blue-600"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="space-y-6">
            <div className="rounded-3xl border border-white/10 bg-black/30 p-6 space-y-4 backdrop-blur-md shadow-xl">
               <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                 <Terminal className="h-4 w-4" />
                 Fleet Status
               </h3>
               <div className="space-y-3">
                  <div className="flex items-center justify-between p-3 rounded-2xl bg-white/5 border border-white/5">
                     <div className="flex items-center gap-2 text-xs text-zinc-400">
                       <Clock className="h-3.5 w-3.5 text-blue-400" />
                       Active
                     </div>
                     <span className="text-lg font-bold text-white">{summary.running}</span>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-2xl bg-white/5 border border-white/5">
                     <div className="flex items-center gap-2 text-xs text-zinc-400">
                       <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                       Success
                     </div>
                     <span className="text-lg font-bold text-emerald-400">{summary.completed}</span>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-2xl bg-white/5 border border-white/5">
                     <div className="flex items-center gap-2 text-xs text-zinc-400">
                       <AlertCircle className="h-3.5 w-3.5 text-red-400" />
                       Failed
                     </div>
                     <span className="text-lg font-bold text-red-400">{summary.failed}</span>
                  </div>
               </div>
            </div>

            {sessions.length > 0 && (
              <div className="rounded-3xl border border-white/10 bg-black/30 p-6 space-y-4 backdrop-blur-md shadow-xl">
                 <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                   <History className="h-4 w-4" />
                   Recent History
                 </h3>
                 <div className="space-y-2 max-h-[400px] overflow-auto pr-2 custom-scrollbar">
                    {sessions.slice(0, 15).map((s) => (
                      <button
                        key={s.id}
                        onClick={() => handleSelectSession(s.id)}
                        className="w-full text-left p-3 rounded-xl border border-white/5 bg-white/5 hover:bg-white/10 hover:border-white/20 transition-all group relative overflow-hidden"
                      >
                         <div className="flex justify-between items-center mb-1">
                           <span className="text-[10px] font-mono text-zinc-500">{s.id.slice(0, 8)}</span>
                           <span className={cn(
                             "text-[10px] font-bold uppercase tracking-tighter",
                             s.status === 'running' ? "text-blue-400 animate-pulse" :
                             s.status === 'completed' ? "text-emerald-500" :
                             s.status === 'failed' ? "text-red-500" : "text-zinc-500"
                           )}>
                             {s.status}
                           </span>
                         </div>
                         <div className="text-xs font-medium text-zinc-200 line-clamp-2 group-hover:text-white transition-colors">
                           {s.goal || "Untitled session"}
                         </div>
                         {sessionId === s.id && (
                           <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-500" />
                         )}
                      </button>
                    ))}
                 </div>
              </div>
            )}
          </div>
        </div>
      )}

      {view === 'live' && activeSession && (
        <div className="space-y-6 animate-in fade-in zoom-in-95 duration-500 pb-20">
          {/* Status Bar */}
          <div className="flex items-center justify-between px-6 py-3 bg-zinc-900/80 border border-white/10 rounded-2xl backdrop-blur-xl shadow-xl">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-3">
                <div className={cn(
                  "h-2.5 w-2.5 rounded-full",
                  status === 'running' ? "bg-blue-500 animate-pulse shadow-[0_0_10px_rgba(59,130,246,0.5)]" :
                  status === 'paused' ? "bg-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.5)]" :
                  status === 'completed' ? "bg-emerald-500" : 
                  status === 'cancelled' ? "bg-zinc-500" : "bg-red-500"
                )} />
                <span className="text-xs font-bold uppercase tracking-widest text-zinc-300">
                  {status === 'running' ? 'Agent Active' : 
                   status === 'paused' ? 'Waiting for Input' : 
                   status === 'completed' ? 'Task Completed' : 
                   status === 'cancelled' ? 'Task Cancelled' : 'Execution Failed'}
                </span>
              </div>
              <div className="h-4 w-px bg-white/10" />
              <div className="flex items-center gap-2 text-[10px] font-mono text-zinc-500">
                <Activity className="h-3 w-3" />
                {activeSession.id.slice(0, 13)}
              </div>
            </div>

                          <div className="flex items-center gap-3">

                            <Button

                              variant={isDebugOpen ? "secondary" : "ghost"}

                              size="sm"

                              onClick={() => setIsDebugOpen(!isDebugOpen)}

                              className="h-8 text-[10px] font-bold uppercase tracking-tight text-zinc-400 hover:text-white"

                            >

                              <Terminal className="h-3.5 w-3.5 mr-2" />

                              Debug Log

                            </Button>

                          </div>

                        </div>

            

                        <div className="grid grid-cols-1 lg:grid-cols-5 gap-8 items-start">

            
            {/* Left Column: Conversation */}
            <div className="lg:col-span-3 space-y-6">
              <Card className="border-white/5 bg-zinc-900/40 rounded-3xl overflow-hidden shadow-2xl flex flex-col h-[850px]">
                <CardHeader className="py-4 px-6 border-b border-white/5 bg-white/[0.02]">
                  <CardTitle className="text-xs font-bold uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                    <MessageSquare className="h-4 w-4 text-blue-500" />
                    Session Conversation
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex-1 overflow-y-auto p-6 space-y-8 custom-scrollbar bg-black/10">
                  {/* Initial Goal Message */}
                  <div className="flex gap-4">
                    <div className="h-8 w-8 rounded-xl bg-blue-600 flex items-center justify-center shrink-0 shadow-lg">
                      <User className="h-4 w-4 text-white" />
                    </div>
                    <div className="space-y-1">
                      <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-tighter">Mission Goal</div>
                      <div className="p-4 bg-blue-600/10 border border-blue-500/20 rounded-2xl rounded-tl-none text-sm text-zinc-200 leading-relaxed max-w-[90%]">
                        {activeSession.goal}
                      </div>
                    </div>
                  </div>

                  {/* Conversation History */}
                  {conversation.map((event, i) => {
                    if (event.type === 'agent') {
                      const payload = event.payload as AgentPayload;
                      const msg = payload.messages?.find((m: AgentMessage) => m.role === 'assistant');
                      
                      if (payload.is_finished) {
                        return (
                          <div key={i} className="flex gap-4 animate-in fade-in slide-in-from-left-4 duration-500">
                            <div className="h-8 w-8 rounded-xl bg-emerald-600/20 border border-emerald-500/20 flex items-center justify-center shrink-0 shadow-lg">
                              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                            </div>
                            <div className="space-y-1">
                              <div className="text-[10px] font-bold text-emerald-500 uppercase tracking-tighter">Mission Accomplished</div>
                              <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-2xl rounded-tl-none text-sm text-zinc-200 leading-relaxed italic">
                                {payload.summary || "Task completed successfully."}
                              </div>
                            </div>
                          </div>
                        );
                      }

                      if (!msg) return null;

                      return (
                        <div key={i} className="space-y-4 animate-in fade-in slide-in-from-left-4 duration-500">
                          {/* Text Commentary */}
                          {msg.content && (
                            <div className="flex gap-4">
                              <div className="h-8 w-8 rounded-xl bg-zinc-800 border border-white/10 flex items-center justify-center shrink-0 shadow-lg">
                                <Bot className="h-4 w-4 text-emerald-400" />
                              </div>
                              <div className="space-y-1 max-w-[90%]">
                                <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-tighter italic">Astra Intelligence</div>
                                <div className="p-4 bg-white/5 border border-white/5 rounded-2xl rounded-tl-none text-sm text-zinc-300 leading-relaxed shadow-sm">
                                  {typeof msg.content === 'string' && msg.content.trim() !== '' ? (
                                    <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={markdownComponents}>
                                      {msg.content}
                                    </ReactMarkdown>
                                  ) : null}
                                </div>
                              </div>
                            </div>
                          )}

                          {/* Tool Proposals */}
                          {msg.tool_calls?.map((tc, tcIdx: number) => (
                            <div key={`${i}-tc-${tcIdx}`} className="flex gap-4 ml-12 animate-in fade-in zoom-in-95 duration-300 max-w-[90%]">
                              <div className="p-1.5 rounded-lg bg-purple-500/10 border border-purple-500/20 h-fit mt-1 shrink-0">
                                <Code2 className="h-3 w-3 text-purple-400" />
                              </div>
                              <div className="space-y-1.5 flex-1 min-w-0 overflow-hidden">
                                <div className="text-[9px] font-bold text-purple-400 uppercase tracking-widest flex items-center gap-2">
                                  Proposing Action
                                  <div className="h-1 w-1 rounded-full bg-purple-500 animate-pulse" />
                                </div>
                                <div className="p-3 bg-purple-500/5 border border-purple-500/10 rounded-xl font-mono text-[11px] text-zinc-400 overflow-hidden">
                                  <div className="text-purple-300 font-bold">{tc.name}</div>
                                  <div className="text-zinc-600 mt-1 break-all whitespace-pre-wrap">{JSON.stringify(tc.args, null, 2)}</div>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      );
                    }

                    if (event.type === 'tools') {
                      const payload = event.payload as AgentPayload;
                      const toolMsg = payload.messages?.[0];
                      if (!toolMsg) return null;
                      
                      // Refined error detection: check for specific system error prefixes
                      const content = typeof toolMsg.content === 'string' ? toolMsg.content : '';
                      const isError = content.startsWith('Error (') || content.startsWith('System Error:');

                      return (
                        <div key={i} className="flex gap-4 ml-12 animate-in fade-in slide-in-from-bottom-2 duration-300">
                          <div className={cn(
                            "p-1.5 rounded-lg h-fit mt-1 border",
                            isError ? "bg-red-500/10 border-red-500/20" : "bg-emerald-500/10 border-emerald-500/20"
                          )}>
                            <Activity className={cn("h-3 w-3", isError ? "text-red-400" : "text-emerald-400")} />
                          </div>
                          <div className="space-y-1.5 flex-1">
                            <div className={cn(
                              "text-[9px] font-bold uppercase tracking-widest",
                              isError ? "text-red-400" : "text-emerald-400"
                            )}>
                              {isError ? 'Tool Error' : 'Operation Result'}
                            </div>
                            <div className={cn(
                              "p-3 rounded-xl font-mono text-[11px] max-h-[150px] overflow-y-auto custom-scrollbar border",
                              isError ? "bg-red-500/5 border-red-500/10 text-red-200/70" : "bg-emerald-500/5 border-emerald-500/10 text-zinc-400"
                            )}>
                              <pre className="whitespace-pre-wrap break-all">{toolMsg.content}</pre>
                            </div>
                          </div>
                        </div>
                      );
                    }

                    if (event.type === 'interrupt' && (event.payload as InterruptPayload).action === 'wait_for_user') {
                      return (
                        <div key={i} className="flex flex-row-reverse gap-4 animate-in fade-in slide-in-from-right-4 duration-500">
                          <div className="h-8 w-8 rounded-xl bg-amber-600 flex items-center justify-center shrink-0 shadow-lg">
                            <User className="h-4 w-4 text-white" />
                          </div>
                          <div className="space-y-1 text-right flex flex-col items-end max-w-[90%]">
                            <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-tighter">Human Validation</div>
                            <div className="p-4 bg-amber-600/10 border border-amber-500/20 rounded-2xl rounded-tr-none text-sm text-zinc-200 leading-relaxed italic">
                              {(event.payload as InterruptPayload).description || "Manual intervention completed."}
                            </div>
                          </div>
                        </div>
                      );
                    }

                    if (event.type === 'human_input') {
                      const payload = event.payload as HumanInputPayload;
                      const content = payload.human_input?.message || payload.message;
                      return (
                        <div key={i} className="flex flex-row-reverse gap-4 animate-in fade-in slide-in-from-right-4 duration-500">
                          <div className="h-8 w-8 rounded-xl bg-blue-600 flex items-center justify-center shrink-0 shadow-lg">
                            <User className="h-4 w-4 text-white" />
                          </div>
                          <div className="space-y-1 text-right flex flex-col items-end max-w-[90%]">
                            <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-tighter">User Message</div>
                            <div className="p-4 bg-blue-600/10 border border-blue-500/20 rounded-2xl rounded-tr-none text-sm text-zinc-200 leading-relaxed">
                              {content}
                            </div>
                          </div>
                        </div>
                      );
                    }
                    return null;
                  })}

                                      {/* Validation UI */}

                                      {status === 'paused' && (

                                        <div className="space-y-4 animate-in slide-in-from-bottom-4 duration-500 pb-4">

                                          <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-2xl flex items-center justify-between backdrop-blur-md shadow-lg">

                                            <div className="flex items-center gap-4">

                                              <div className="p-2 bg-amber-500/20 rounded-xl">

                                                <ShieldCheck className="h-5 w-5 text-amber-500" />

                                              </div>

                                              <div>

                                                <div className="text-amber-500 text-sm font-bold uppercase tracking-tight">Validation Required</div>

                                                <div className="text-amber-200/70 text-xs font-medium italic">

                                                  {latestInterrupt?.description || "The agent requires authorization to proceed."}

                                                </div>

                                              </div>

                                            </div>

                                            <div className="flex items-center gap-3">

                                              <Button 

                                                variant="ghost"

                                                onClick={handleCancel}

                                                className="text-red-400 hover:text-red-300 hover:bg-red-500/10 h-10 rounded-xl px-6 font-bold transition-all"

                                              >

                                                Reject

                                              </Button>

                                              <Button 

                                                onClick={handleResume} 

                                                disabled={isResuming}

                                                className="bg-amber-500 hover:bg-amber-600 text-black font-bold rounded-xl h-10 px-6 transition-all shadow-lg shadow-amber-900/20"

                                              >

                                                {isResuming ? (

                                                  <div className="flex items-center gap-2">

                                                    <div className="h-3 w-3 rounded-full border-2 border-black border-t-transparent animate-spin" />

                                                    Resuming...

                                                  </div>

                                                ) : (

                                                  "Approve & Continue"

                                                )}

                                              </Button>

                                            </div>

                                          </div>

                  

                                                                  {/* Tool Argument Widget (Nested) */}

                  

                                                                  {latestInterrupt && latestInterrupt.action !== 'wait_for_user' && (

                  

                                                                    <div className="p-6 bg-zinc-900/80 border border-white/10 rounded-2xl backdrop-blur-xl shadow-xl space-y-4 ml-12">

                  

                                                                      <div className="flex items-center justify-between">

                  

                                                                        <div className="flex items-center gap-2">

                  

                                                                          <div className="p-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20">

                  

                                                                            {latestInterrupt.action === 'run_shell' ? <Terminal className="h-4 w-4 text-blue-400" /> : 

                  

                                                                             latestInterrupt.action === 'write_file' ? <Code2 className="h-4 w-4 text-blue-400" /> :

                  

                                                                             latestInterrupt.action === 'ask_user' ? <MessageSquare className="h-4 w-4 text-blue-400" /> :

                  

                                                                             <Settings2 className="h-4 w-4 text-blue-400" />}

                  

                                                                          </div>

                  

                                                                          <h4 className="text-sm font-bold text-zinc-200 uppercase tracking-widest">

                  

                                                                            {latestInterrupt.action === 'ask_user' ? 'Agent Question' : `Proposed ${latestInterrupt.action.replace('_', ' ')}`}

                  

                                                                          </h4>

                  

                                                                        </div>

                  

                                                                        <div className="text-[10px] font-mono text-zinc-500">

                  

                                                                          {new Date(latestInterrupt.timestamp).toLocaleTimeString()}

                  

                                                                        </div>

                  

                                                                      </div>

                  

                                          

                  

                                                                      <div className="space-y-3">

                  

                                                                                                      {latestInterrupt.action === 'ask_user' && (

                  

                                                                                                        <div className="p-4 bg-blue-500/5 border border-blue-500/20 rounded-xl space-y-4">

                  

                                                                                                          <p className="text-sm text-zinc-200 font-medium leading-relaxed">

                  

                                                                                                            {latestInterrupt.question}

                  

                                                                                                          </p>

                  

                                                                                                          

                  

                                                                                                          {latestInterrupt.choices && Array.isArray(latestInterrupt.choices) && (

                  

                                                                                                            <div className="flex flex-wrap gap-2 pt-2">

                  

                                                                                                              {latestInterrupt.choices.map((choice: string, idx: number) => (

                  

                                                                                                                <Button

                  

                                                                                                                  key={idx}

                  

                                                                                                                  variant="secondary"

                  

                                                                                                                  size="sm"

                  

                                                                                                                  onClick={async () => {

                  

                                                                                                                    setIsSendingMessage(true);

                  

                                                                                                                    try {

                  

                                                                                                                      await sendMessage(choice);

                  

                                                                                                                    } catch (err) {

                  

                                                                                                                      console.error("Failed to send choice:", err);

                  

                                                                                                                    } finally {

                  

                                                                                                                      setIsSendingMessage(false);

                  

                                                                                                                    }

                  

                                                                                                                  }}

                  

                                                                                                                  className="bg-blue-600/20 hover:bg-blue-600/40 border-blue-500/30 text-blue-300 text-xs rounded-lg px-4 h-8 transition-all"

                  

                                                                                                                >

                  

                                                                                                                  {choice}

                  

                                                                                                                </Button>

                  

                                                                                                              ))}

                  

                                                                                                            </div>

                  

                                                                                                          )}

                  

                                                                        

                  

                                                                                                          <p className="mt-3 text-[10px] text-zinc-500 italic">

                  

                                                                                                            {latestInterrupt.choices ? "Select an option above or type your own answer below." : "Type your answer in the chat box below to resume."}

                  

                                                                                                          </p>

                  

                                                                                                        </div>

                  

                                                                                                      )}

                  

                                                                        

                  

                                          

                  

                                                                        {latestInterrupt.action === 'run_shell' && (

                  

                                          

                                                  <div className="space-y-2">

                                                    <div className="text-[10px] font-bold text-zinc-500 uppercase">Command</div>

                                                    <div className="p-4 bg-black/40 rounded-xl border border-white/5 font-mono text-xs text-blue-300 break-all">

                                                      {latestInterrupt.command}

                                                    </div>

                                                    {latestInterrupt.cwd && (

                                                      <div className="flex items-center gap-2">

                                                        <span className="text-[10px] font-bold text-zinc-600 uppercase">Directory:</span>

                                                        <span className="text-[10px] font-mono text-zinc-400">{latestInterrupt.cwd}</span>

                                                      </div>

                                                    )}

                                                  </div>

                                                )}

                  

                                                {latestInterrupt.action === 'write_file' && (() => {
                                                  const filePath = latestInterrupt.path as string || '';
                                                  const isImage = /\.(png|jpg|jpeg|gif|webp|svg|bmp|ico)$/i.test(filePath);
                                                  const isPdf = /\.pdf$/i.test(filePath);

                                                  return (
                                                    <div className="space-y-2">
                                                      <div className="flex items-center justify-between">
                                                        <div className="text-[10px] font-bold text-zinc-500 uppercase">Target Path</div>
                                                        <span className="text-[10px] font-mono text-zinc-400">{filePath}</span>
                                                      </div>

                                                      {isImage || isPdf ? (
                                                        <div className="space-y-2">
                                                          <div className="text-[10px] font-bold text-zinc-500 uppercase">File Type</div>
                                                          <div className="p-4 bg-black/40 rounded-xl border border-white/5 text-xs text-amber-300">
                                                            <div className="flex items-center gap-2">
                                                              <FileText className="h-4 w-4" />
                                                              <span>
                                                                {isImage ? 'Image file' : 'PDF document'} - Preview not available for binary files.
                                                                File will be written to: <span className="font-mono text-blue-300">{filePath}</span>
                                                              </span>
                                                            </div>
                                                          </div>
                                                        </div>
                                                      ) : (
                                                        <>
                                                          <div className="text-[10px] font-bold text-zinc-500 uppercase">Content Preview</div>
                                                          <div className="p-4 bg-black/40 rounded-xl border border-white/5 font-mono text-xs text-emerald-300 overflow-x-hidden max-h-[300px] overflow-y-auto custom-scrollbar">
                                                            <pre className="whitespace-pre-wrap break-words">{latestInterrupt.content_preview}</pre>
                                                          </div>
                                                        </>
                                                      )}
                                                    </div>
                                                  );
                                                })()}

                  

                                                {latestInterrupt.action === 'user_takeover' && (

                                                  <div className="p-4 bg-red-500/5 border border-red-500/20 rounded-xl">

                                                    <div className="text-[10px] font-bold text-red-400 uppercase mb-1">Reason for Takeover</div>

                                                    <p className="text-sm text-zinc-300 italic">"{latestInterrupt.reason}"</p>

                                                  </div>

                                                )}

                  

                                                {/* Generic JSON fallback for other tools */}

                                                {!['run_shell', 'write_file', 'user_takeover'].includes(latestInterrupt.action) && (

                                                  <div className="space-y-2">

                                                    <div className="text-[10px] font-bold text-zinc-500 uppercase">Arguments</div>

                                                    <div className="p-4 bg-black/40 rounded-xl border border-white/5 font-mono text-[10px] text-zinc-400">

                                                      <pre>{JSON.stringify(latestInterrupt, null, 2)}</pre>

                                                    </div>

                                                  </div>

                                                )}

                                              </div>

                                            </div>

                                          )}

                                        </div>

                                      )}

                  

                                      {/* Typing Indicator */}

                  
                  {status === 'running' && (
                    <div className="flex gap-4 animate-pulse">
                      <div className="h-8 w-8 rounded-xl bg-zinc-800 border border-white/10 flex items-center justify-center shrink-0">
                        <Bot className="h-4 w-4 text-zinc-600" />
                      </div>
                      <div className="flex items-center gap-1.5 px-4 py-3 bg-white/5 rounded-2xl rounded-tl-none border border-white/5">
                        <div className="h-1.5 w-1.5 rounded-full bg-zinc-600 animate-bounce [animation-delay:-0.3s]" />
                        <div className="h-1.5 w-1.5 rounded-full bg-zinc-600 animate-bounce [animation-delay:-0.15s]" />
                        <div className="h-1.5 w-1.5 rounded-full bg-zinc-600 animate-bounce" />
                      </div>
                    </div>
                  )}
                  <div ref={scrollRef} />
                </CardContent>

                {/* Chat Input Area */}
                <div className="p-4 border-t border-white/5 bg-black/20 space-y-3">
                  <div className="flex items-center justify-between px-1">
                    <div className="flex items-center gap-2">
                      <Switch 
                        id="live-validation-mode"
                        checked={validationRequired}
                        onCheckedChange={setValidationRequired}
                        className="data-[state=checked]:bg-blue-600 scale-75 origin-left"
                      />
                      <Label htmlFor="live-validation-mode" className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 cursor-pointer">
                        {validationRequired ? "Validated Execution" : "Full Automatic"}
                      </Label>
                    </div>
                    {status === 'paused' && (
                      <div className="text-[10px] text-amber-500 font-bold uppercase animate-pulse">
                        Waiting for Approval
                      </div>
                    )}
                  </div>

                  <div className="flex gap-3">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setIsUploadModalOpen(true)}
                      className="h-10 w-10 shrink-0 rounded-xl border border-white/5 bg-white/5 text-zinc-400 hover:text-white"
                      title="Upload file"
                    >
                      <Upload className="h-4 w-4" />
                    </Button>
                    <div className="relative flex-1">
                      <Input
                        value={messageInput}
                        onChange={(e) => setMessageInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            handleSendMessage();
                          }
                        }}
                        placeholder={status === 'running' ? "Agent is working..." : "Send a message or instruction..."}
                        disabled={status === 'running' || isSendingMessage}
                        className="h-10 bg-black/40 border-white/10 rounded-xl pr-12 focus:ring-blue-500/50 transition-all text-sm"
                      />
                      <Button
                        size="icon"
                        variant="ghost"
                        onClick={handleSendMessage}
                        disabled={!messageInput.trim() || status === 'running' || isSendingMessage}
                        className="absolute right-1 top-1 h-8 w-8 rounded-lg text-blue-400 hover:text-blue-300 disabled:opacity-30"
                      >
                        {isSendingMessage ? (
                          <div className="h-3 w-3 rounded-full border-2 border-blue-400 border-t-transparent animate-spin" />
                        ) : (
                          <ChevronRight className="h-5 w-5" />
                        )}
                      </Button>
                    </div>
                    {(status === 'running' || status === 'paused') && (
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={handleCancel}
                        className="h-10 w-10 shrink-0 rounded-xl border border-red-500/20 bg-red-500/5 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                        title="Cancel Run"
                      >
                        <Square className="h-3 w-3 fill-current" />
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            </div>

            {/* Right Column: Operations & Status */}
            <div className="lg:col-span-2 space-y-8">
              <Card className="border-white/5 bg-zinc-900/50 rounded-3xl overflow-hidden shadow-xl flex flex-col max-h-[500px]">
                <CardHeader className="py-4 px-6 border-b border-white/5 bg-white/[0.02] flex flex-row items-center justify-between shrink-0">
                  <div className="flex items-center gap-2">
                    <ListTodo className="h-4 w-4 text-blue-500" />
                    <CardTitle className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Autonomous Plan</CardTitle>
                  </div>
                  <div className="flex bg-black/40 p-1 rounded-lg border border-white/5">
                    <button 
                      onClick={() => setPlanTab('checklist')}
                      className={cn(
                        "px-2 py-1 rounded text-[9px] font-bold uppercase transition-all",
                        planTab === 'checklist' ? "bg-white/10 text-white shadow-lg" : "text-zinc-500 hover:text-zinc-300"
                      )}
                    >
                      Checklist
                    </button>
                    <button 
                      onClick={() => setPlanTab('markdown')}
                      className={cn(
                        "px-2 py-1 rounded text-[9px] font-bold uppercase transition-all",
                        planTab === 'markdown' ? "bg-white/10 text-white shadow-lg" : "text-zinc-500 hover:text-zinc-300"
                      )}
                    >
                      Strategy
                    </button>
                  </div>
                </CardHeader>
                <CardContent className="p-4 space-y-3 overflow-y-auto custom-scrollbar">
                  {planSteps.length === 0 && !rawPlan ? (
                    <div className="p-4 bg-black/40 rounded-2xl border border-white/5 italic text-zinc-500 text-xs text-center">
                      Agent is formulating strategy...
                    </div>
                  ) : planTab === 'checklist' ? (
                    planSteps.map((step: PlanStep, idx: number) => (
                      <div key={idx} className={cn(
                        "p-3 rounded-xl border transition-all",
                        step.status === 'completed' ? "bg-emerald-500/5 border-emerald-500/20 opacity-60" :
                        step.status === 'in_progress' ? "bg-blue-500/10 border-blue-500/30 shadow-[0_0_15px_rgba(59,130,246,0.1)]" :
                        "bg-white/5 border-white/5"
                      )}>
                        <div className="flex items-start gap-3">
                          <div className="mt-0.5 shrink-0">
                            {step.status === 'completed' ? (
                              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                            ) : step.status === 'in_progress' ? (
                              <div className="h-4 w-4 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
                            ) : (
                              <Circle className="h-4 w-4 text-zinc-700" />
                            )}
                          </div>
                          <div className="space-y-1">
                            <div className={cn(
                              "text-xs font-bold leading-none",
                              step.status === 'completed' ? "text-emerald-500/80 line-through" :
                              step.status === 'in_progress' ? "text-blue-400" : "text-zinc-400"
                            )}>
                              {step.title}
                            </div>
                            <p className="text-[10px] text-zinc-500 leading-tight">
                              {step.description}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))
                                                                                                                         ) : (
                                                                                                                           <div className="text-zinc-400 font-mono leading-relaxed px-2">
                                                                                                                             {typeof rawPlan === 'string' && rawPlan.trim() !== '' ? (
                                                                                                                               <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={markdownComponents}>
                                                                                                                                 {rawPlan}
                                                                                                                               </ReactMarkdown>
                                                                                                                             ) : null}
                                                                                                                           </div>
                                                          
                                                          )}
                                                      </CardContent>
              </Card>

              <Card className="border-white/5 bg-zinc-900/50 rounded-3xl overflow-hidden shadow-xl flex flex-col max-h-[400px]">
                <CardHeader className="py-4 px-6 border-b border-white/5 bg-white/[0.02]">
                  <div className="flex items-center gap-2">
                    <Box className="h-4 w-4 text-blue-500" />
                    <CardTitle className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Workspace Files</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="p-4 space-y-1 overflow-y-auto custom-scrollbar">
                  {fileTree.length === 0 ? (
                    <div className="p-8 text-center space-y-3">
                      <Box className="h-8 w-8 text-zinc-700 mx-auto" />
                      <p className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">No workspace artifacts yet</p>
                    </div>
                  ) : (
                    fileTree.map((file, idx) => (
                      <div 
                        key={idx}
                        className="flex items-center justify-between p-2 rounded-lg bg-white/5 border border-white/5 hover:bg-white/10 transition-all group"
                      >
                        <div className="flex items-center gap-2 overflow-hidden">
                          <FileText className="h-3.5 w-3.5 text-blue-400 shrink-0" />
                          <span className="text-[11px] text-zinc-300 truncate font-mono">{file}</span>
                        </div>
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-zinc-500 hover:text-blue-400"
                            title="Preview"
                            onClick={() => handlePreviewFile(file)}
                          >
                            <Eye className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-zinc-500 hover:text-emerald-400"
                            title="Download"
                            onClick={() => {
                              if (activeSession?.sandbox_session) {
                                window.open(`/api/sandbox/sessions/${activeSession.sandbox_session}/files/content?path=${encodeURIComponent(file)}`, '_blank');
                              }
                            }}
                          >
                            <Download className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>

              <Card className="border-white/5 bg-zinc-900/50 rounded-3xl overflow-hidden shadow-xl flex-1 flex flex-col min-h-[300px]">
                <CardHeader className="py-4 px-6 border-b border-white/5 bg-white/[0.02]">
                  <CardTitle className="text-xs font-bold uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                    <Activity className="h-4 w-4 text-blue-500" />
                    Visual Environment
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex-1 flex flex-col items-center justify-center bg-black p-0 relative group">
                  <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/20 to-transparent z-10 flex flex-col justify-end p-8 space-y-2">
                    <h4 className="text-white font-bold text-lg tracking-tight text-shadow-sm">System Virtualization</h4>
                    <p className="text-[10px] text-zinc-500 uppercase tracking-[0.2em] font-medium flex items-center gap-2">
                      <Terminal className="h-3 w-3" /> 
                      Awaiting Frame Stream...
                    </p>
                  </div>
                  <div className="relative">
                    <div className="w-16 h-16 border-4 border-zinc-900 border-t-blue-500 rounded-full animate-spin shadow-[0_0_20px_rgba(59,130,246,0.2)]"></div>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="w-8 h-8 bg-blue-500/10 rounded-full blur-xl animate-pulse"></div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>

          {/* Collapsible Debug Console (Terminal Log) */}
          {isDebugOpen && (
            <div className="fixed bottom-0 left-0 right-0 z-50 animate-in slide-in-from-bottom-full duration-500 ease-out">
              <Card className="mx-auto w-[95%] max-w-[clamp(72rem,85vw,120rem)] border-white/10 bg-zinc-950 rounded-t-3xl overflow-hidden shadow-[0_-20px_50px_rgba(0,0,0,0.5)] border-b-0 h-[400px] flex flex-col">
                <CardHeader className="py-3 px-6 border-b border-white/10 bg-zinc-900 flex flex-row items-center justify-between shrink-0">
                  <div className="flex items-center gap-3">
                    <Terminal className="h-4 w-4 text-blue-500" />
                    <CardTitle className="text-xs font-bold uppercase tracking-widest text-zinc-300">Raw System Stream (Debug Console)</CardTitle>
                  </div>
                  <Button 
                    variant="ghost" 
                    size="sm" 
                    onClick={() => setIsDebugOpen(false)}
                    className="h-8 w-8 p-0 rounded-xl hover:bg-white/5"
                  >
                    <ChevronDown className="h-4 w-4 text-zinc-500" />
                  </Button>
                </CardHeader>
                <CardContent className="flex-1 overflow-y-auto p-6 space-y-4 font-mono text-[11px] custom-scrollbar bg-black/40">
                  {events.map((event, i) => (
                    <div key={i} className="group border-l border-white/5 pl-4 py-0.5 hover:border-blue-500/30 transition-all">
                      <div className="flex items-center space-x-3 mb-1">
                        <span className={cn(
                          "px-1.5 py-0.5 rounded text-[8px] font-black uppercase tracking-tight border",
                          event.type === 'agent' ? "bg-blue-500/10 text-blue-400 border-blue-500/20" :
                          event.type === 'tools' ? "bg-purple-500/10 text-purple-400 border-purple-500/20" :
                          event.type === 'interrupt' ? "bg-amber-500/10 text-amber-400 border-amber-500/20" :
                          "bg-zinc-500/10 text-zinc-400 border-zinc-500/20"
                        )}>
                          {event.type}
                        </span>
                        <span className="text-[9px] text-zinc-700 font-medium">{new Date(event.timestamp).toLocaleTimeString()}</span>
                      </div>
                      <pre className="whitespace-pre-wrap break-all text-zinc-500 leading-relaxed">
                        {typeof event.payload === 'string' 
                          ? event.payload 
                          : JSON.stringify(event.payload, null, 2)}
                      </pre>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      )}
      
            {view === 'live' && !activeSession && (
      
              <div className="flex flex-col items-center justify-center py-40 text-center space-y-6">
      
                 <div className="h-24 w-24 rounded-full bg-white/5 flex items-center justify-center border border-white/10 shadow-2xl">
      
                    <Terminal className="h-10 w-10 text-zinc-600" />
      
                 </div>
      
                 <div className="space-y-2">
      
                    <h3 className="text-2xl font-bold text-white tracking-tight">No active deployment</h3>
      
                    <p className="text-zinc-500 text-sm max-w-xs mx-auto">Please select a session from the history or launch a new autonomous agent.</p>
      
                 </div>
      
                 <Button 
      
                  className="rounded-xl h-11 px-8 font-bold bg-zinc-100 text-black hover:bg-white transition-all" 
      
                  onClick={() => setView("setup")}
      
                 >
      
                   Return to Command Center
      
                 </Button>
      
              </div>
      
            )}
      
      
      
            {/* File Upload Dialog */}
      
            <Dialog open={isUploadModalOpen} onOpenChange={setIsUploadModalOpen}>
      
              <DialogContent className="sm:max-w-[425px] bg-zinc-900 border-white/10 text-zinc-100">
      
                <DialogHeader>
      
                  <DialogTitle className="flex items-center gap-2">
      
                    <Upload className="h-5 w-5 text-blue-500" />
      
                    Upload file to sandbox
      
                  </DialogTitle>
      
                  <DialogDescription className="text-zinc-500">
      
                    Transfer a file from your local system into the agent's workspace.
      
                  </DialogDescription>
      
                </DialogHeader>
      
                <div className="grid gap-6 py-4">
      
                  <div className="grid gap-2">
      
                    <Label htmlFor="file" className="text-xs uppercase tracking-widest text-zinc-500 font-bold">Local File</Label>
      
                    <Input
      
                      id="file"
      
                      type="file"
      
                      onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
      
                      disabled={isUploading}
      
                      className="bg-black/40 border-white/10 h-10 text-xs"
      
                    />
      
                  </div>
      
                  <div className="grid gap-2">
      
                    <Label htmlFor="path" className="text-xs uppercase tracking-widest text-zinc-500 font-bold">Target Path</Label>
      
                    <div className="relative">
      
                      <Paperclip className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500" />
      
                      <Input
      
                        id="path"
      
                        placeholder="filename.ext or folder/file.ext"
      
                        value={uploadPath}
      
                        onChange={(e) => setUploadPath(e.target.value)}
      
                        disabled={isUploading}
      
                        className="bg-black/40 border-white/10 h-10 pl-10 text-xs"
      
                      />
      
                    </div>
      
                    {uploadTarget.error ? (
      
                      <p className="text-[10px] text-red-400 font-medium">{uploadTarget.error}</p>
      
                    ) : (
      
                      <p className="text-[10px] text-zinc-500 italic">
      
                        {selectedFile 
      
                          ? `Will be uploaded to: ${uploadTarget.path}`
      
                          : "Files must be stored within /workspace"}
      
                      </p>
      
                    )}
      
                  </div>
      
                </div>
      
                <DialogFooter>
      
                  <Button 
      
                    variant="ghost" 
      
                    onClick={() => setIsUploadModalOpen(false)}
      
                    className="text-zinc-400 hover:text-white"
      
                  >
      
                    Cancel
      
                  </Button>
      
                  <Button
      
                    onClick={handleUploadFile}
      
                    disabled={isUploading || !selectedFile || !!uploadTarget.error}
      
                    className="bg-blue-600 hover:bg-blue-500 text-white font-bold px-6"
      
                  >
      
                    {isUploading ? (
      
                      <div className="flex items-center gap-2">
      
                        <div className="h-3 w-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
      
                        Uploading...
      
                      </div>
      
                    ) : (
      
                      "Upload"
      
                    )}
      
                  </Button>
      
                </DialogFooter>
      
              </DialogContent>
      
                  </Dialog>

            {/* File Preview Dialog */}
            <Dialog open={!!previewFilePath} onOpenChange={(open) => !open && setPreviewFilePath(null)}>
              <DialogContent className="sm:max-w-[80vw] max-h-[80vh] bg-zinc-900 border-white/10 text-zinc-100 flex flex-col">
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2">
                    <FileText className="h-5 w-5 text-blue-500" />
                    Preview: {previewFilePath?.split('/').pop()}
                  </DialogTitle>
                  <DialogDescription className="text-zinc-500 font-mono text-[10px] truncate">
                    {previewFilePath}
                  </DialogDescription>
                </DialogHeader>
                
                <div className="flex-1 overflow-auto bg-black/40 rounded-xl border border-white/5 p-6 custom-scrollbar min-h-[300px]">
                  {isPreviewLoading ? (
                    <div className="h-full flex flex-col items-center justify-center space-y-4">
                      <div className="w-10 h-10 border-2 border-zinc-800 border-t-blue-500 rounded-full animate-spin"></div>
                      <p className="text-xs text-zinc-500 animate-pulse">Reading file content...</p>
                    </div>
                                        ) : (
                                          <div>
                                            {previewContent === "__IMAGE__" ? (
                                              <div className="flex items-center justify-center">
                                                <img
                                                  src={`/api/sandbox/sessions/${encodeURIComponent(activeSession?.sandbox_session || '')}/files/content/?path=${encodeURIComponent(previewFilePath || '')}`}
                                                  alt={previewFilePath?.split('/').pop() || 'Preview'}
                                                  className="max-w-full max-h-[60vh] object-contain rounded-lg"
                                                  onError={() => {
                                                    console.error('Failed to load image');
                                                    toast.error('Failed to load image');
                                                  }}
                                                />
                                              </div>
                                            ) : previewFilePath?.endsWith('.md') ? (
                                              typeof previewContent === 'string' && previewContent.trim() !== '' ? (
                                                <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={markdownComponents}>
                                                  {previewContent}
                                                </ReactMarkdown>
                                              ) : null
                                            ) : (
                                              <pre className="text-[11px] leading-relaxed font-mono whitespace-pre-wrap break-all text-zinc-300">
                                                {previewContent}
                                              </pre>
                                            )}
                                          </div>
                                        )}
                  
                </div>

                <DialogFooter className="sm:justify-between items-center border-t border-white/5 pt-4">
                  <div className="text-[10px] text-zinc-500 italic">
                    {previewContent && previewContent !== "__IMAGE__" ? `${previewContent.length} characters` : ""}
                  </div>
                  <Button
                    variant="secondary"
                    onClick={() => setPreviewFilePath(null)}
                    className="rounded-xl h-9 px-6 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border-white/5"
                  >
                    Close
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>

      {/* Document Upload Modal */}
      <Dialog open={isDocUploadModalOpen} onOpenChange={setIsDocUploadModalOpen}>
        <DialogContent className="bg-zinc-900 border-white/10 text-zinc-100 max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl flex items-center gap-2">
              <Upload className="h-5 w-5 text-blue-400" />
              Upload Documents
            </DialogTitle>
            <DialogDescription className="text-zinc-400">
              Add documents (PDF, CSV, code files, etc.) to provide context for the agent. Max 5 files, 10MB each.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="border-2 border-dashed border-white/10 rounded-xl p-8 text-center">
              <input
                type="file"
                multiple
                onChange={(e) => handleAddDocFiles(e.target.files)}
                className="hidden"
                id="doc-file-input"
                accept=".pdf,.txt,.csv,.json,.md,.py,.js,.jsx,.ts,.tsx,.java,.c,.cpp,.h,.hpp,.html,.css,.xml,.yaml,.yml,.toml,.ini,.conf,.sh,.bash,.sql,.log,.png,.jpg,.jpeg,.gif,.svg,.webp,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip,.tar,.gz"
              />
              <label htmlFor="doc-file-input" className="cursor-pointer">
                <Upload className="h-12 w-12 mx-auto mb-4 text-zinc-500" />
                <p className="text-sm text-zinc-400 mb-2">Click to select files or drag and drop</p>
                <p className="text-xs text-zinc-500">PDF, TXT, CSV, JSON, Code files, Images</p>
              </label>
            </div>

            {docFiles.length > 0 && (
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {docFiles.map((file, idx) => (
                  <div key={idx} className="p-4 rounded-lg bg-white/5 border border-white/5 space-y-3">
                    <div className="flex items-center gap-3">
                      <FileText className="h-5 w-5 text-blue-400 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-zinc-200 truncate">{file.name}</p>
                        <p className="text-xs text-zinc-500">{(file.size / 1024).toFixed(2)} KB</p>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveDocFile(idx)}
                        className="h-8 w-8 p-0 hover:bg-red-500/20 flex-shrink-0"
                      >
                        <span className="text-red-400">×</span>
                      </Button>
                    </div>
                    <Input
                      placeholder="Optional: Add description or context for this file"
                      value={docDescriptions[idx.toString()] || ''}
                      onChange={(e) => handleDocDescriptionChange(idx, e.target.value)}
                      className="bg-black/40 border-white/10 text-sm"
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => {
                setIsDocUploadModalOpen(false);
                setDocFiles([]);
                setDocDescriptions({});
              }}
              className="rounded-xl h-9 px-6"
            >
              Cancel
            </Button>
            <Button
              onClick={handleUploadDocuments}
              disabled={docFiles.length === 0 || uploadingDoc}
              className="rounded-xl h-9 px-6 bg-blue-600 hover:bg-blue-500"
            >
              {uploadingDoc ? 'Uploading...' : `Upload ${docFiles.length} File${docFiles.length !== 1 ? 's' : ''}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
      
            
      
      