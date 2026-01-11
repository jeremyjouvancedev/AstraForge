import { useMemo, useState, useEffect, useRef } from "react";
import {
  Clock,
  Download,
  Maximize2,
  Globe,
  Search,
  MousePointer2,
  Keyboard,
  ArrowUpDown,
  Command,
  ArrowLeft,
  XCircle,
  Eye,
  Shield,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Info,
  History,
  Loader2
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
} from "@/components/ui/dialog";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { type ComputerUseRun, type ComputerUseTimelineItem } from "@/lib/api-client";

interface ComputerUseRunViewProps {
  run: ComputerUseRun;
  timelineItems: ComputerUseTimelineItem[];
  onApprove: (acknowledged: string[]) => void;
  onDeny: () => void;
  isActionPending: boolean;
  onExport: () => void;
}

type LogicalStep = {
  callId: string;
  stepIndex: number;
  actionItem?: ComputerUseTimelineItem;
  outputItem?: ComputerUseTimelineItem;
  policyItems: ComputerUseTimelineItem[];
  ackItems: ComputerUseTimelineItem[];
  debugInfo?: Record<string, unknown>;
  url?: string;
};

function normalizeString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function getActionIcon(type: string) {
  const t = type.toLowerCase();
  if (t.includes("visit_url")) return <Globe className="h-3.5 w-3.5" />;
  if (t.includes("search")) return <Search className="h-3.5 w-3.5" />;
  if (t.includes("click")) return <MousePointer2 className="h-3.5 w-3.5" />;
  if (t.includes("type")) return <Keyboard className="h-3.5 w-3.5" />;
  if (t.includes("scroll")) return <ArrowUpDown className="h-3.5 w-3.5" />;
  if (t.includes("key")) return <Command className="h-3.5 w-3.5" />;
  if (t.includes("wait")) return <Clock className="h-3.5 w-3.5" />;
  if (t.includes("back")) return <ArrowLeft className="h-3.5 w-3.5" />;
  if (t.includes("terminate")) return <Loader2 className="h-3.5 w-3.5 animate-spin" />;
  return <Info className="h-3.5 w-3.5" />;
}

function formatActionSummary(action: Record<string, unknown>) {
  const type = normalizeString(action.type).toLowerCase();
  if (!type) return "Action details unavailable";
  if (type === "visit_url") return normalizeString(action.url) || "Navigate to URL";
  if (type === "web_search") return normalizeString(action.query) || "Search the web";
  if (type === "type") return normalizeString(action.text) === "[REDACTED]" ? "Typed redacted text" : `Type: ${normalizeString(action.text)}`;
  if (type === "click" || type === "double_click") return `Click at ${action.x}, ${action.y}`;
  return type.replace(/_/g, " ");
}

/**
 * Groups raw timeline items into logical execution steps
 */
function buildLogicalSteps(items: ComputerUseTimelineItem[]): LogicalStep[] {
  const stepsList: LogicalStep[] = [];
  const stepsMap = new Map<string, LogicalStep>();

  items.forEach((item) => {
    const callId = normalizeString(item.call_id);
    if (!callId) return;

    if (!stepsMap.has(callId)) {
      const newStep: LogicalStep = {
        callId,
        stepIndex: 0,
        policyItems: [],
        ackItems: []
      };
      stepsMap.set(callId, newStep);
      stepsList.push(newStep);
    }

    const step = stepsMap.get(callId)!;
    if (item.type === "computer_call") {
      step.actionItem = item;
      if (item.debug_info) {
        step.debugInfo = item.debug_info as Record<string, unknown>;
      }
    } else if (item.type === "computer_call_output") {
      step.outputItem = item;
      step.url = (item.output as Record<string, unknown>)?.url as string | undefined;
    } else if (item.type === "policy_decision") {
      step.policyItems.push(item);
    } else if (item.type === "acknowledged_safety_checks") {
      step.ackItems.push(item);
    }
  });

  return stepsList.map((s, idx) => ({ ...s, stepIndex: idx + 1 }));
}

function statusTone(status?: string | null) {
  const value = (status || "").toLowerCase();
  if (value.includes("awaiting")) return "bg-amber-500/15 text-amber-300";
  if (value.includes("running")) return "bg-primary/15 text-primary";
  if (value.includes("completed")) return "bg-emerald-500/15 text-emerald-400 animate-pulse-slow";
  if (value.includes("blocked") || value.includes("denied")) return "bg-destructive/15 text-destructive";
  return "bg-muted/70 text-muted-foreground";
}

function severityTone(severity?: string | null) {
  if (severity === "high") return "bg-destructive/15 text-destructive";
  if (severity === "medium") return "bg-amber-500/15 text-amber-300";
  return "bg-emerald-500/15 text-emerald-400";
}

export function ComputerUseRunView({
  run,
  timelineItems,
  onApprove,
  onDeny,
  isActionPending,
  onExport
}: ComputerUseRunViewProps) {
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [isFullscreenOpen, setIsFullscreenOpen] = useState(false);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const [isDebugOpen, setIsDebugOpen] = useState(false);
  const [acknowledgedChecks, setAcknowledgedChecks] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  const logicalSteps = useMemo(() => buildLogicalSteps(timelineItems), [timelineItems]);
  
  const latestStepId = useMemo(() => {
    if (logicalSteps.length === 0) return null;
    return logicalSteps[logicalSteps.length - 1].callId;
  }, [logicalSteps]);

  useEffect(() => {
    if (selectedStepId === null && latestStepId !== null) {
      setSelectedStepId(latestStepId);
    }
  }, [latestStepId, selectedStepId]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logicalSteps.length]);

  const selectedStep = useMemo(() => 
    logicalSteps.find(s => s.callId === selectedStepId), 
  [logicalSteps, selectedStepId]);

  const selectedScreenshot = (selectedStep?.outputItem?.output as Record<string, unknown>)?.screenshot_b64 as string | undefined;

  const pendingChecks = run.pending_checks ?? [];
  const ackReady = pendingChecks.every((check) => acknowledgedChecks.includes(check.id));

  const toggleCheck = (id: string, checked: boolean) => {
    setAcknowledgedChecks((curr) => checked ? [...curr, id] : curr.filter((x) => x !== id));
  };

  const domainGroups = useMemo(() => {
    const groups: Array<{ domain: string; steps: LogicalStep[] }> = [];
    logicalSteps.forEach((step) => {
      const url = step.url || (step.actionItem?.action as Record<string, unknown>)?.url as string | undefined || "Initializing";
      const domain = url.includes("://") ? new URL(url).hostname : url;
      
      if (groups.length > 0 && groups[groups.length - 1].domain === domain) {
        groups[groups.length - 1].steps.push(step);
      } else {
        groups.push({ domain, steps: [step] });
      }
    });
    return groups;
  }, [logicalSteps]);

  return (
    <div className="h-[calc(100vh-12rem)] min-h-[600px] w-full">
      <div className="flex items-center justify-between mb-4 px-2">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold text-white tracking-tight">Agent Session</h2>
          <Badge className={cn("rounded-full px-3", statusTone(run.status))}>
            {run.status.replace(/_/g, " ")}
          </Badge>
        </div>
        <div className="flex gap-2">
           <Button 
            variant="outline" 
            size="sm" 
            onClick={() => setIsDebugOpen(!isDebugOpen)} 
            className={cn("h-8 border-white/10 bg-white/5", isDebugOpen ? "text-amber-400 border-amber-400/30" : "text-zinc-400")}
           >
             <Shield className="h-3.5 w-3.5 mr-2" />
             Debug
           </Button>
           <Button variant="outline" size="sm" onClick={onExport} className="h-8 border-white/10 bg-white/5 text-zinc-400">
             <Download className="h-3.5 w-3.5 mr-2" />
             Export Trace
           </Button>
        </div>
      </div>

      <ResizablePanelGroup direction="horizontal" className="rounded-3xl border border-white/10 bg-black/20 overflow-hidden shadow-2xl">
        {/* Left: Logical History */}
        <ResizablePanel defaultSize={30} minSize={20}>
          <div className="h-full flex flex-col border-r border-white/10">
            <div className="p-4 border-b border-white/10 bg-white/5 space-y-3">
              <div className="flex items-center gap-2">
                <Shield className="h-3.5 w-3.5 text-indigo-400" />
                <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Active Goal</span>
              </div>
              <p className="text-xs font-medium text-zinc-200 leading-relaxed italic">
                "{run.goal}"
              </p>
            </div>
            
            <div className="p-4 border-b border-white/10 bg-white/5 flex items-center gap-2">
              <History className="h-3.5 w-3.5 text-zinc-500" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Execution Timeline</span>
            </div>
            <div className="flex-1 overflow-auto p-3 space-y-6" ref={scrollRef}>
                {domainGroups.map((group, gIdx) => (
                  <div key={gIdx} className="space-y-2">
                    <div className="flex items-center gap-2 px-2">
                      <Globe className="h-3 w-3 text-indigo-400/50" />
                      <span className="text-[10px] font-bold text-zinc-500 truncate">{group.domain}</span>
                      <div className="flex-1 h-[1px] bg-white/5" />
                    </div>
                    
                    <div className="space-y-1.5">
                      {group.steps.map((step) => {
                        const actionType = normalizeString((step.actionItem?.action as Record<string, unknown>)?.type) || "Event";
                        const isSelected = selectedStepId === step.callId;
                        const hasPolicy = step.policyItems.length > 0;
                        
                        return (
                          <button
                            key={step.callId}
                            onClick={() => setSelectedStepId(step.callId)}
                            className={cn(
                              "w-full text-left p-2 rounded-xl border transition-all duration-200 group relative",
                              isSelected
                                ? "bg-indigo-500/10 border-indigo-500/40 shadow-lg shadow-indigo-500/5"
                                : "bg-black/10 border-white/5 hover:border-white/10 hover:bg-white/5"
                            )}
                          >
                            <div className="flex items-center gap-3">
                               <div className={cn(
                                 "p-1.5 rounded-lg border flex items-center justify-center shrink-0",
                                 isSelected ? "bg-indigo-500/20 border-indigo-500/30 text-indigo-300" : "bg-white/5 border-white/10 text-zinc-500"
                               )}>
                                  {getActionIcon(actionType)}
                               </div>
                               <div className="min-w-0 flex-1">
                                  <div className="text-[11px] font-semibold text-zinc-200 truncate">
                                    {formatActionSummary((step.actionItem?.action as Record<string, unknown>) || {})}
                                  </div>
                                  <div className="flex items-center gap-2 mt-0.5">
                                     <span className="text-[9px] text-zinc-600">Step {step.stepIndex}</span>
                                     {hasPolicy && <Shield className="h-2.5 w-2.5 text-amber-500/50" />}
                                     {step.outputItem && <CheckCircle2 className="h-2.5 w-2.5 text-emerald-500/50" />}
                                  </div>
                               </div>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle className="bg-white/10" />

        {/* Right: Step Deep Dive */}
        <ResizablePanel defaultSize={isDebugOpen ? 40 : 70} minSize={30}>
          <ScrollArea className="h-full bg-black/40">
            <div className="p-8">
              {run.status === "completed" && (
                <div className="max-w-4xl mx-auto mb-6 flex items-center justify-center">
                  <div className="flex items-center gap-3 px-4 py-2 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span className="text-xs font-bold uppercase tracking-widest">Terminating Session...</span>
                  </div>
                </div>
              )}
              
              {run.final_response && (
                <div className="max-w-4xl mx-auto mb-8 animate-in fade-in slide-in-from-top-4 duration-500">
                  <div className="rounded-3xl border border-emerald-500/30 bg-emerald-500/5 p-6 shadow-xl shadow-emerald-500/5">
                    <div className="flex items-center gap-3 mb-4">
                      <div className="h-10 w-10 rounded-2xl bg-emerald-500/20 flex items-center justify-center text-emerald-400">
                        <CheckCircle2 className="h-5 w-5" />
                      </div>
                      <div>
                        <h3 className="text-sm font-bold text-white uppercase tracking-widest">Final Conclusion</h3>
                        <p className="text-[10px] text-emerald-400/60 font-medium">Task successfully completed</p>
                      </div>
                    </div>
                    <div className="text-zinc-100 leading-relaxed font-medium">
                      <ReactMarkdown 
                        remarkPlugins={[remarkGfm]}
                        components={{
                          h1: ({ ...props }) => <h1 {...props} className="text-2xl font-bold mb-4 text-white" />,
                          h2: ({ ...props }) => <h2 {...props} className="text-xl font-bold mb-3 text-white" />,
                          h3: ({ ...props }) => <h3 {...props} className="text-lg font-bold mb-2 text-white" />,
                          p: ({ ...props }) => <p {...props} className="mb-4 last:mb-0" />,
                          ul: ({ ...props }) => <ul {...props} className="list-disc pl-6 mb-4 space-y-1" />,
                          ol: ({ ...props }) => <ol {...props} className="list-decimal pl-6 mb-4 space-y-1" />,
                          li: ({ ...props }) => <li {...props} className="leading-relaxed" />,
                          code: ({ ...props }) => <code {...props} className="bg-emerald-500/20 px-1.5 py-0.5 rounded text-emerald-300 font-mono text-[0.9em]" />,
                          pre: ({ ...props }) => <pre {...props} className="bg-black/40 p-4 rounded-2xl border border-white/5 overflow-x-auto mb-4" />,
                          a: ({ ...props }) => <a {...props} className="text-emerald-400 underline hover:text-emerald-300 transition-colors" target="_blank" rel="noreferrer" />,
                          strong: ({ ...props }) => <strong {...props} className="font-bold text-white" />,
                          blockquote: ({ ...props }) => <blockquote {...props} className="border-l-4 border-emerald-500/50 pl-4 italic text-zinc-300 mb-4" />,
                        }}
                      >
                        {run.final_response}
                      </ReactMarkdown>
                    </div>
                  </div>
                </div>
              )}

              {selectedStep ? (
                <div className="max-w-4xl mx-auto space-y-8">
                  {/* Observation Preview (The Result) */}
                  <div className="space-y-4">
                     <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                           <div className="h-8 w-8 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                              <Eye className="h-4 w-4" />
                           </div>
                           <div>
                              <h3 className="text-sm font-bold text-white uppercase tracking-wider">Browser State</h3>
                              <p className="text-xs text-zinc-500 font-mono truncate max-w-md">{selectedStep.url || "Initializing..."}</p>
                           </div>
                        </div>
                        {selectedScreenshot && (
                          <Button variant="ghost" size="sm" onClick={() => setIsFullscreenOpen(true)} className="text-indigo-400 hover:text-indigo-300">
                             <Maximize2 className="h-4 w-4 mr-2" />
                             Fullscreen
                          </Button>
                        )}
                     </div>

                     {selectedScreenshot ? (
                        <div 
                          className="relative rounded-3xl border border-white/10 bg-black overflow-hidden cursor-zoom-in shadow-2xl group"
                          onClick={() => setIsFullscreenOpen(true)}
                        >
                          <img
                            src={`data:image/png;base64,${selectedScreenshot}`}
                            alt="Screenshot"
                            className="w-full h-auto transition-transform duration-700 group-hover:scale-[1.005]"
                          />
                        </div>
                     ) : (
                        <div className="aspect-video rounded-3xl border border-dashed border-white/10 bg-white/5 flex flex-col items-center justify-center text-zinc-600 space-y-2">
                          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-500" />
                          <span className="text-xs italic">Capturing browser state...</span>
                        </div>
                     )}
                  </div>

                  {/* Intent & Action */}
                  <div className="grid grid-cols-1 md:grid-cols-[1fr,300px] gap-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                    <div className="space-y-6">
                       <div className="space-y-2">
                          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-400">Reasoning</span>
                          <p className="text-lg text-zinc-100 leading-relaxed font-medium">
                            {normalizeString((selectedStep.actionItem?.meta as Record<string, unknown>)?.reasoning_summary) || "Processing logic..."}
                          </p>
                       </div>

                       <div className="p-4 rounded-2xl bg-white/5 border border-white/10 space-y-3">
                          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-500">Action Execution</span>
                          <div className="flex items-center gap-3">
                             <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400">
                                {getActionIcon(normalizeString((selectedStep.actionItem?.action as Record<string, unknown>)?.type))}
                             </div>
                             <span className="text-sm font-semibold text-white">
                               {formatActionSummary((selectedStep.actionItem?.action as Record<string, unknown>) || {})}
                             </span>
                          </div>
                       </div>
                    </div>

                    <div className="space-y-6">
                       {/* Policy Integration */}
                       {run.status === "awaiting_ack" && selectedStepId === latestStepId && (
                          <div className="p-5 rounded-2xl border-amber-500/30 bg-amber-500/5 space-y-4 shadow-xl">
                            <div className="flex items-center gap-2 text-amber-300">
                              <Shield className="h-4 w-4" />
                              <h4 className="text-xs font-bold uppercase tracking-widest">Safety Gate</h4>
                            </div>
                            
                            {pendingChecks.length > 0 && (
                               <div className="space-y-2">
                                 {pendingChecks.map((check) => (
                                   <div key={check.id} className="flex items-start gap-2.5 p-2 rounded-lg bg-black/40 border border-white/5">
                                      <Checkbox 
                                        id={check.id} 
                                        checked={acknowledgedChecks.includes(check.id)}
                                        onCheckedChange={(val) => toggleCheck(check.id, !!val)}
                                        className="mt-0.5 border-amber-500/50"
                                      />
                                      <div className="min-w-0">
                                        <div className="flex items-center gap-1.5 mb-0.5">
                                           <Badge className={cn("text-[8px] h-3 px-1", severityTone(check.severity))}>{check.severity}</Badge>
                                           <span className="text-[8px] text-zinc-500 uppercase">{check.category}</span>
                                        </div>
                                        <p className="text-[11px] text-zinc-300 leading-tight">{check.message}</p>
                                      </div>
                                   </div>
                                 ))}
                               </div>
                            )}

                            <div className="flex flex-col gap-2">
                              <Button 
                                className="w-full bg-amber-600 hover:bg-amber-500 text-white font-bold h-9 text-xs rounded-xl" 
                                disabled={!ackReady || isActionPending}
                                onClick={() => onApprove(acknowledgedChecks)}
                              >
                                {isActionPending ? "Approving..." : "Confirm & Resume"}
                              </Button>
                              <Button 
                                variant="ghost" 
                                className="w-full h-8 text-xs text-zinc-500 hover:text-red-400"
                                onClick={onDeny}
                              >
                                Stop Run
                              </Button>
                            </div>
                          </div>
                       )}

                       {/* Metadata Collapsible */}
                       <Collapsible open={isDetailsOpen} onOpenChange={setIsDetailsOpen} className="space-y-2">
                          <CollapsibleTrigger asChild>
                            <Button variant="ghost" size="sm" className="w-full justify-between h-8 text-[10px] font-bold uppercase tracking-widest text-zinc-500 px-2">
                              System Specs
                              {isDetailsOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                            </Button>
                          </CollapsibleTrigger>
                          <CollapsibleContent className="space-y-2">
                             <div className="p-3 rounded-xl bg-white/5 border border-white/10 space-y-3">
                                <div className="space-y-1">
                                   <div className="text-[8px] text-zinc-600 uppercase">Call Identity</div>
                                   <div className="text-[10px] font-mono text-zinc-400 break-all">{selectedStep.callId}</div>
                                </div>
                             </div>
                          </CollapsibleContent>
                       </Collapsible>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="h-full flex flex-col items-center justify-center py-24 space-y-4">
                  <div className="h-16 w-16 rounded-3xl bg-white/5 border border-white/10 flex items-center justify-center">
                    <History className="h-8 w-8 text-zinc-500 opacity-20" />
                  </div>
                  <div className="text-center">
                    <p className="text-zinc-400 font-medium">Timeline Analysis</p>
                    <p className="text-xs text-zinc-600">Select a step to inspect reasoning and browser state</p>
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>
        </ResizablePanel>

        {isDebugOpen && (
          <>
            <ResizableHandle withHandle className="bg-white/10" />
            <ResizablePanel defaultSize={30} minSize={20}>
              <div className="h-full flex flex-col bg-zinc-950/50 min-w-0">
                <div className="p-4 border-b border-white/10 bg-white/5 flex items-center justify-between shrink-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <Shield className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                    <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 truncate">LLM Debug Context</span>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => setIsDebugOpen(false)} className="h-6 w-6 p-0 rounded-full shrink-0">
                    <XCircle className="h-4 w-4 text-zinc-600" />
                  </Button>
                </div>
                <ScrollArea className="flex-1 min-h-0">
                  <div className="p-4 space-y-6">
                    {selectedStep?.debugInfo ? (
                      <div className="space-y-4 min-w-0">
                        <div className="flex items-center justify-between px-2 gap-2">
                           <div className="text-[10px] text-zinc-500 truncate">Model: <span className="text-zinc-300 font-mono">{selectedStep.debugInfo.model}</span></div>
                           <div className="text-[10px] text-zinc-500 truncate">Provider: <span className="text-zinc-300 font-mono">{selectedStep.debugInfo.provider}</span></div>
                        </div>
                        
                        <div className="space-y-4">
                          {(selectedStep.debugInfo.messages as Array<{ 
                            type: string; 
                            data?: { content?: unknown; tool_calls?: Array<{ name: string; args: unknown }> };
                            content?: string;
                          }> || []).map((msg, mIdx) => (
                            <div key={mIdx} className={cn(
                              "p-3 rounded-2xl border text-[11px] space-y-2 min-w-0 overflow-hidden",
                              msg.type === "human" ? "bg-indigo-500/5 border-indigo-500/20" : 
                              msg.type === "ai" ? "bg-emerald-500/5 border-emerald-500/20" : 
                              "bg-white/5 border-white/10"
                            )}>
                              <div className="flex items-center justify-between">
                                <span className="font-bold uppercase tracking-tighter opacity-50">{msg.type}</span>
                              </div>
                              <div className="space-y-2 min-w-0">
                                {Array.isArray(msg.data?.content) ? (
                                  (msg.data.content as Array<{ type: string; text?: string; image_url?: { url: string } }>).map((c, cIdx) => (
                                    <div key={cIdx} className="min-w-0">
                                      {c.type === "text" && <div className="whitespace-pre-wrap font-mono break-words">{c.text}</div>}
                                      {c.type === "image_url" && (
                                        <div className="mt-2 rounded-lg border border-white/10 overflow-hidden bg-black max-w-full">
                                          <img src={c.image_url?.url} alt="LLM input" className="max-w-full h-auto opacity-70" />
                                        </div>
                                      )}
                                    </div>
                                  ))
                                ) : (
                                  <div className="whitespace-pre-wrap font-mono break-words">{msg.data?.content as string || msg.content}</div>
                                )}
                                
                                {msg.data?.tool_calls?.map((tc, tcIdx) => (
                                  <div key={tcIdx} className="mt-2 p-2 rounded-lg bg-black/40 border border-white/5 font-mono text-[10px] min-w-0 overflow-hidden">
                                    <div className="text-indigo-400 font-bold truncate">Tool Call: {tc.name}</div>
                                    <pre className="mt-1 text-zinc-400 overflow-x-auto whitespace-pre-wrap break-words">{JSON.stringify(tc.args, null, 2)}</pre>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center py-20 text-center space-y-3 opacity-30">
                        <Info className="h-8 w-8" />
                        <p className="text-xs">No LLM debug info available for this step.</p>
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </div>
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>

      <Dialog open={isFullscreenOpen} onOpenChange={setIsFullscreenOpen}>
        <DialogContent className="max-w-[95vw] w-full max-h-[95vh] h-full p-0 bg-black/95 border-white/10 overflow-hidden">
          <div className="w-full h-full flex flex-col">
             <div className="p-4 border-b border-white/10 bg-black/40 flex items-center justify-between">
                <div className="flex items-center gap-3">
                   <Globe className="h-4 w-4 text-indigo-400" />
                   <span className="text-xs font-mono text-zinc-400">{selectedStep?.url}</span>
                </div>
                <Button variant="ghost" size="sm" onClick={() => setIsFullscreenOpen(false)} className="text-zinc-500">Close</Button>
             </div>
             <div className="flex-1 flex items-center justify-center p-4 overflow-auto scrollbar-hide">
                <img
                  src={`data:image/png;base64,${selectedScreenshot}`}
                  alt="Fullscreen"
                  className="max-w-none w-auto h-auto object-contain"
                />
             </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}