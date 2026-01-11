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
  Info
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { type ComputerUseRun, type ComputerUseTimelineItem } from "@/lib/api-client";

interface ComputerUseRunViewProps {
  run: ComputerUseRun;
  timelineItems: ComputerUseTimelineItem[];
  onApprove: (acknowledged: string[]) => void;
  onDeny: () => void;
  isActionPending: boolean;
  onExport: () => void;
}

type TimelineEntry = {
  index: number;
  step: number | null;
  title: string;
  subtitle: string;
  kind: "call" | "output" | "policy" | "ack" | "other";
  item: ComputerUseTimelineItem;
};

function normalizeString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function getActionIcon(type: string, kind: string) {
  const t = type.toLowerCase();
  if (kind === "policy") return <Shield className="h-3.5 w-3.5" />;
  if (kind === "ack") return <CheckCircle2 className="h-3.5 w-3.5" />;
  if (kind === "output") return <Eye className="h-3.5 w-3.5" />;

  if (t.includes("visit_url")) return <Globe className="h-3.5 w-3.5" />;
  if (t.includes("search")) return <Search className="h-3.5 w-3.5" />;
  if (t.includes("click")) return <MousePointer2 className="h-3.5 w-3.5" />;
  if (t.includes("type")) return <Keyboard className="h-3.5 w-3.5" />;
  if (t.includes("scroll")) return <ArrowUpDown className="h-3.5 w-3.5" />;
  if (t.includes("key")) return <Command className="h-3.5 w-3.5" />;
  if (t.includes("wait")) return <Clock className="h-3.5 w-3.5" />;
  if (t.includes("back")) return <ArrowLeft className="h-3.5 w-3.5" />;
  if (t.includes("terminate")) return <XCircle className="h-3.5 w-3.5" />;
  
  return <Info className="h-3.5 w-3.5" />;
}

function formatActionSummary(action: Record<string, unknown>) {
  const type = normalizeString(action.type).toLowerCase();
  if (!type) return "Action details unavailable";
  if (type === "visit_url") {
    return normalizeString(action.url) || "Navigate to URL";
  }
  if (type === "web_search") {
    const query = normalizeString(action.query);
    return query ? `Search: ${query}` : "Search the web";
  }
  if (type === "type") {
    const text = normalizeString(action.text);
    const hash = normalizeString(action.text_sha256);
    if (text === "[REDACTED]") {
      return hash ? `Typed text (redacted · ${hash.slice(0, 8)})` : "Typed text (redacted)";
    }
    return text ? `Typed: ${text}` : "Typed text";
  }
  if (type === "click" || type === "double_click") {
    const x = action.x;
    const y = action.y;
    if (typeof x === "number" && typeof y === "number") {
      return `Click at x:${x}, y:${y}`;
    }
    return "Click";
  }
  if (type === "scroll") {
    const dx = action.scroll_dx;
    const dy = action.scroll_dy;
    if (typeof dx === "number" || typeof dy === "number") {
      return `Scroll dx:${dx ?? 0}, dy:${dy ?? 0}`;
    }
    return "Scroll";
  }
  if (type === "keypress") {
    const keys = Array.isArray(action.keys) ? action.keys.join("+") : "";
    return keys ? `Keys: ${keys}` : "Keypress";
  }
  if (type === "wait") {
    const seconds = action.seconds;
    if (typeof seconds === "number") {
      return `Wait ${seconds}s`;
    }
    return "Wait";
  }
  if (type === "back") {
    return "Navigate back";
  }
  if (type === "terminate") {
    return "Terminate run";
  }
  return type.replace(/_/g, " ");
}

function buildTimelineEntries(items: ComputerUseTimelineItem[]): TimelineEntry[] {
  const entries: TimelineEntry[] = [];
  let stepCounter = 0;

  items.forEach((item, index) => {
    const type = normalizeString(item.type) || "event";
    let step = stepCounter + 1;
    let title = type.replace(/_/g, " ");
    let subtitle = "";
    let kind: TimelineEntry["kind"] = "other";

    if (type === "computer_call") {
      const action = (item.action ?? {}) as Record<string, unknown>;
      const meta = (item.meta ?? {}) as Record<string, unknown>;
      const reasoning = normalizeString(meta.reasoning_summary);
      const actionType = normalizeString(action.type).replace(/_/g, " ") || "action";
      title = actionType;
      subtitle = reasoning || formatActionSummary(action);
      kind = "call";
    } else if (type === "computer_call_output") {
      stepCounter += 1;
      step = stepCounter;
      const output = (item.output ?? {}) as Record<string, unknown>;
      const url = normalizeString(output.url);
      title = "Observation";
      subtitle = url || "Observation captured";
      kind = "output";
    } else if (type === "policy_decision") {
      const decision = normalizeString(item.decision) || "decision";
      const checks = Array.isArray(item.checks) ? item.checks.length : 0;
      title = `Policy: ${decision.replace(/_/g, " ")}`;
      const reason = normalizeString(item.reason);
      subtitle = reason ? `Reason: ${reason}` : `${checks} checks`;
      kind = "policy";
    } else if (type === "acknowledged_safety_checks") {
      const decision = normalizeString(item.decision) || "decision";
      const acknowledged = Array.isArray(item.acknowledged) ? item.acknowledged.length : 0;
      title = `Approval: ${decision.replace(/_/g, " ")}`;
      subtitle = `${acknowledged} checks acknowledged`;
      kind = "ack";
    }

    entries.push({
      index,
      step: step || null,
      title,
      subtitle,
      kind,
      item
    });
  });

  return entries;
}

function timelineTone(kind: TimelineEntry["kind"]) {
  if (kind === "call") return "bg-indigo-500/15 text-indigo-200 border-indigo-500/30";
  if (kind === "output") return "bg-emerald-500/15 text-emerald-300 border-emerald-500/30";
  if (kind === "policy") return "bg-amber-500/15 text-amber-200 border-amber-500/30";
  if (kind === "ack") return "bg-sky-500/15 text-sky-200 border-sky-500/30";
  return "bg-muted/70 text-muted-foreground border-transparent";
}

function statusTone(status?: string | null) {
  const value = (status || "").toLowerCase();
  if (value.includes("awaiting")) return "bg-amber-500/15 text-amber-300";
  if (value.includes("running")) return "bg-primary/15 text-primary";
  if (value.includes("completed")) return "bg-emerald-500/15 text-emerald-400";
  if (value.includes("blocked") || value.includes("denied")) return "bg-destructive/15 text-destructive";
  return "bg-muted/70 text-muted-foreground";
}

function severityTone(severity?: string | null) {
  if (!severity) return "bg-muted/70 text-muted-foreground";
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
  const [selectedEntryIndex, setSelectedEntryIndex] = useState<number | null>(null);
  const [isFullscreenOpen, setIsFullscreenOpen] = useState(false);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const [acknowledgedChecks, setAcknowledgedChecks] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  const timelineEntries = useMemo(() => buildTimelineEntries(timelineItems), [timelineItems]);
  
  const latestOutputIndex = useMemo(() => {
    for (let idx = timelineEntries.length - 1; idx >= 0; idx -= 1) {
      if (timelineEntries[idx].kind === "output") return idx;
    }
    return timelineEntries.length > 0 ? timelineEntries.length - 1 : null;
  }, [timelineEntries]);

  useEffect(() => {
    if (selectedEntryIndex === null && latestOutputIndex !== null) {
      setSelectedEntryIndex(latestOutputIndex);
    }
  }, [latestOutputIndex, selectedEntryIndex]);

  // Auto-scroll to bottom on new items
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [timelineItems.length]);

  const selectedEntry = selectedEntryIndex !== null ? timelineEntries[selectedEntryIndex] : null;
  const selectedItem = selectedEntry?.item;
  const selectedOutput = selectedItem?.type === "computer_call_output" ? selectedItem.output : null;
  const selectedScreenshot = selectedOutput?.screenshot_b64;

  const pendingChecks = run.pending_checks ?? [];
  const ackReady = pendingChecks.every((check) => acknowledgedChecks.includes(check.id));

  const toggleCheck = (id: string, checked: boolean) => {
    setAcknowledgedChecks((curr) => checked ? [...curr, id] : curr.filter((x) => x !== id));
  };

  const primaryInfo = useMemo(() => {
    if (!selectedEntry || !selectedItem) return null;
    if (selectedItem.type === "computer_call") {
      const action = (selectedItem.action ?? {}) as Record<string, unknown>;
      const meta = (selectedItem.meta ?? {}) as Record<string, unknown>;
      return {
        type: normalizeString(action.type),
        summary: formatActionSummary(action),
        reasoning: normalizeString(meta.reasoning_summary)
      };
    }
    if (selectedItem.type === "computer_call_output" && selectedOutput) {
       return {
         type: "Observation",
         summary: selectedOutput.url ? `At: ${selectedOutput.url}` : "State captured",
         reasoning: null
       };
    }
    return {
      type: selectedEntry.title,
      summary: selectedEntry.subtitle,
      reasoning: null
    };
  }, [selectedEntry, selectedItem, selectedOutput]);

  const technicalDetails = useMemo(() => {
    if (!selectedItem) return [];
    const rows: Array<{ label: string; value: string }> = [];
    
    if (selectedItem.type === "computer_call") {
      const action = (selectedItem.action ?? {}) as Record<string, unknown>;
      Object.entries(action).forEach(([key, value]) => {
        if (key !== "type" && value) rows.push({ label: key, value: String(value) });
      });
      const callId = normalizeString(selectedItem.call_id);
      if (callId) rows.push({ label: "Call ID", value: callId });
    }
    
    if (selectedItem.type === "computer_call_output" && selectedOutput) {
      const exec = (selectedOutput.execution ?? {}) as Record<string, unknown>;
      if (exec.status) rows.push({ label: "Status", value: String(exec.status) });
      if (exec.error_message) rows.push({ label: "Error", value: String(exec.error_message) });
    }

    if (selectedItem.type === "policy_decision") {
      if (selectedItem.reason) rows.push({ label: "Policy Reason", value: String(selectedItem.reason) });
    }
    
    return rows;
  }, [selectedItem, selectedOutput]);

  return (
    <div className="h-[calc(100vh-12rem)] min-h-[600px] w-full">
      <div className="flex items-center justify-between mb-4 px-2">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold text-white">Live Run View</h2>
          <Badge className={cn("rounded-full", statusTone(run.status))}>
            {run.status.replace(/_/g, " ")}
          </Badge>
        </div>
        <div className="flex gap-2">
           <Button variant="outline" size="sm" onClick={onExport} className="h-8 border-white/10 bg-white/5">
             <Download className="h-3.5 w-3.5 mr-2" />
             Export
           </Button>
        </div>
      </div>

      <ResizablePanelGroup direction="horizontal" className="rounded-3xl border border-white/10 bg-black/20 overflow-hidden shadow-2xl">
        {/* Left: History */}
        <ResizablePanel defaultSize={35} minSize={25}>
          <div className="h-full flex flex-col border-r border-white/10">
            <div className="p-4 border-b border-white/10 bg-white/5 flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">History</span>
              <span className="text-[10px] text-zinc-600 font-mono">{timelineEntries.length} items</span>
            </div>
            <div className="flex-1 overflow-auto p-4 space-y-2" ref={scrollRef}>
                {timelineEntries.map((entry) => {
                  const actionType = entry.item.type === "computer_call" 
                    ? normalizeString((entry.item.action as Record<string, unknown>)?.type) 
                    : entry.item.type;
                  
                  return (
                    <button
                      key={entry.index}
                      onClick={() => setSelectedEntryIndex(entry.index)}
                      className={cn(
                        "w-full text-left p-2.5 rounded-xl border transition-all duration-200 group relative",
                        selectedEntryIndex === entry.index
                          ? "bg-indigo-500/10 border-indigo-500/40 shadow-lg shadow-indigo-500/5"
                          : "bg-black/10 border-white/5 hover:border-white/10 hover:bg-white/5"
                      )}
                    >
                      <div className="flex items-start gap-3">
                         <div className={cn(
                           "mt-0.5 p-1.5 rounded-lg border flex items-center justify-center shrink-0 transition-colors",
                           selectedEntryIndex === entry.index ? "bg-indigo-500/20 border-indigo-500/30 text-indigo-300" : "bg-white/5 border-white/10 text-zinc-500"
                         )}>
                            {getActionIcon(actionType, entry.kind)}
                         </div>
                         <div className="min-w-0 flex-1">
                            <div className="flex items-center justify-between mb-0.5">
                              <span className="text-[9px] font-medium text-zinc-600 uppercase">Step {entry.step}</span>
                              <div className={cn("w-1.5 h-1.5 rounded-full shrink-0", 
                                entry.kind === "call" ? "bg-indigo-500/40" : 
                                entry.kind === "output" ? "bg-emerald-500/40" : 
                                entry.kind === "policy" ? "bg-amber-500/40" : "bg-zinc-700")} 
                              />
                            </div>
                            <div className="text-xs font-semibold text-zinc-200 group-hover:text-white truncate">
                              {entry.title}
                            </div>
                            {entry.subtitle && (
                              <div className="text-[11px] text-zinc-500 mt-0.5 line-clamp-1">
                                {entry.subtitle}
                              </div>
                            )}
                         </div>
                      </div>
                    </button>
                  );
                })}
                {run.status === "running" && (
                   <div className="flex items-center gap-2 p-4 text-[10px] text-zinc-500 animate-pulse">
                     <Clock className="h-3 w-3" />
                     Waiting for next step...
                   </div>
                )}
              </div>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle className="bg-white/10" />

        {/* Right: Detail View */}
        <ResizablePanel defaultSize={65} minSize={40}>
          <ScrollArea className="h-full bg-black/40">
            <div className="p-6 space-y-6">
              {selectedEntry ? (
                <div className="space-y-6 max-w-4xl mx-auto">
                  {/* Screenshot Card */}
                  <div className="space-y-4">
                     {selectedScreenshot ? (
                        <div className="group relative">
                          <div 
                            className="relative rounded-2xl border border-white/10 bg-black overflow-hidden cursor-zoom-in shadow-2xl transition-all duration-300 group-hover:border-indigo-500/30"
                            onClick={() => setIsFullscreenOpen(true)}
                          >
                            <img
                              src={`data:image/png;base64,${selectedScreenshot}`}
                              alt="Screenshot"
                              className="w-full h-auto transition-transform duration-700 group-hover:scale-[1.005]"
                            />
                            <div className="absolute inset-0 bg-indigo-500/0 group-hover:bg-indigo-500/5 transition-colors pointer-events-none" />
                          </div>
                          <Button 
                            variant="secondary" 
                            size="icon" 
                            onClick={() => setIsFullscreenOpen(true)}
                            className="absolute top-4 right-4 h-8 w-8 rounded-full bg-black/60 border-white/10 text-white opacity-0 group-hover:opacity-100 transition-opacity backdrop-blur"
                          >
                             <Maximize2 className="h-4 w-4" />
                          </Button>
                        </div>
                     ) : (
                        <div className="aspect-video rounded-3xl border border-dashed border-white/10 bg-white/5 flex flex-col items-center justify-center text-zinc-500 space-y-2">
                          <Eye className="h-8 w-8 opacity-20" />
                          <span className="text-sm italic">No visual data for this step</span>
                        </div>
                     )}
                  </div>

                  {/* Step Info Section */}
                  <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                    <div className="flex items-start justify-between gap-4">
                       <div className="space-y-1">
                          <div className="flex items-center gap-2">
                             <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-400">Step {selectedEntry.step}</span>
                             <span className="text-zinc-600">•</span>
                             <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-500">{primaryInfo?.type}</span>
                          </div>
                          <h3 className="text-2xl font-semibold text-white tracking-tight">
                            {primaryInfo?.summary}
                          </h3>
                       </div>
                       <Badge variant="outline" className={cn("mt-1 px-3 py-1 border", timelineTone(selectedEntry.kind))}>
                         {selectedEntry.kind}
                       </Badge>
                    </div>

                    {primaryInfo?.reasoning && (
                      <div className="p-4 rounded-2xl bg-indigo-500/5 border border-indigo-500/10 text-sm text-indigo-100/80 leading-relaxed italic">
                         "{primaryInfo.reasoning}"
                      </div>
                    )}

                    {/* Policy / Approval Integration */}
                    {run.status === "awaiting_ack" && selectedEntryIndex === latestOutputIndex && (
                      <Card className="border-amber-500/30 bg-amber-500/5 shadow-xl shadow-amber-900/10 overflow-hidden">
                        <CardContent className="p-5 space-y-4">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2.5 text-amber-300">
                              <Shield className="h-4 w-4" />
                              <h4 className="text-sm font-bold uppercase tracking-wider">Policy Gate</h4>
                            </div>
                            <Badge className="bg-amber-500/20 text-amber-200 border-amber-500/30 text-[10px]">Awaiting Approval</Badge>
                          </div>
                          
                          {pendingChecks.length > 0 && (
                             <div className="space-y-2">
                               {pendingChecks.map((check) => (
                                 <div key={check.id} className="flex items-start gap-3 p-3 rounded-xl bg-black/40 border border-white/5 transition-colors hover:border-amber-500/20">
                                    <Checkbox 
                                      id={check.id} 
                                      checked={acknowledgedChecks.includes(check.id)}
                                      onCheckedChange={(checked) => toggleCheck(check.id, !!checked)}
                                      className="mt-1 border-amber-500/50 data-[state=checked]:bg-amber-500"
                                    />
                                    <div className="space-y-1">
                                      <div className="flex items-center gap-2">
                                        <Badge className={cn("text-[9px] h-3.5 px-1 font-bold", severityTone(check.severity))}>{check.severity}</Badge>
                                        <span className="text-[10px] text-zinc-500 uppercase tracking-widest">{check.category}</span>
                                      </div>
                                      <p className="text-xs text-zinc-300 font-medium">{check.message}</p>
                                    </div>
                                 </div>
                               ))}
                             </div>
                          )}

                          <div className="flex gap-3">
                            <Button 
                              className="flex-1 bg-amber-600 hover:bg-amber-500 text-white font-bold h-10 rounded-xl transition-all" 
                              disabled={!ackReady || isActionPending}
                              onClick={() => onApprove(acknowledgedChecks)}
                            >
                              {isActionPending ? "Processing..." : "Approve Step"}
                            </Button>
                            <Button 
                              variant="ghost" 
                              className="px-6 h-10 rounded-xl text-zinc-400 hover:text-red-400 hover:bg-red-400/10"
                              disabled={isActionPending}
                              onClick={onDeny}
                            >
                              Deny
                            </Button>
                          </div>
                        </CardContent>
                      </Card>
                    )}

                    {/* Technical Details Collapsible */}
                    {technicalDetails.length > 0 && (
                      <Collapsible
                        open={isDetailsOpen}
                        onOpenChange={setIsDetailsOpen}
                        className="space-y-2"
                      >
                        <CollapsibleTrigger asChild>
                          <Button variant="ghost" size="sm" className="p-0 h-auto font-bold text-[10px] uppercase tracking-widest text-zinc-500 hover:text-white transition-colors">
                            {isDetailsOpen ? <ChevronUp className="h-3 w-3 mr-1" /> : <ChevronDown className="h-3 w-3 mr-1" />}
                            Technical Parameters
                          </Button>
                        </CollapsibleTrigger>
                        <CollapsibleContent className="space-y-2 animate-in fade-in slide-in-from-top-1 duration-200">
                          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                            {technicalDetails.map((row) => (
                              <div key={row.label} className="p-3 rounded-xl bg-white/5 border border-white/5 transition-colors hover:bg-white/10">
                                 <div className="text-[9px] uppercase tracking-widest text-zinc-600 mb-1">{row.label}</div>
                                 <div className="text-xs text-zinc-300 break-all font-mono">{row.value}</div>
                              </div>
                            ))}
                          </div>
                        </CollapsibleContent>
                      </Collapsible>
                    )}
                  </div>
                </div>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-zinc-500 space-y-4 py-20">
                  <div className="p-4 rounded-full bg-white/5 border border-white/10 animate-pulse">
                    <MousePointer2 className="h-8 w-8 opacity-20" />
                  </div>
                  <div className="text-center">
                    <h4 className="text-zinc-400 font-medium">No Step Selected</h4>
                    <p className="text-xs text-zinc-600">Select an item from the history to inspect details</p>
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>
        </ResizablePanel>
      </ResizablePanelGroup>

      <Dialog open={isFullscreenOpen} onOpenChange={setIsFullscreenOpen}>
        <DialogContent className="max-w-[95vw] w-full max-h-[95vh] h-full p-0 bg-black/95 border-white/10 shadow-2xl overflow-hidden">
          <div className="w-full h-full flex items-center justify-center p-4 overflow-auto scrollbar-hide">
             <img
                src={`data:image/png;base64,${selectedScreenshot}`}
                alt="Fullscreen"
                className="max-w-none w-auto h-auto object-contain transition-transform duration-500"
             />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}