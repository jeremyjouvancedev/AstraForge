import { useMemo, useState, useEffect, useRef } from "react";
import {
  AlertTriangle,
  Clock,
  Download,
  Maximize2
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

  const selectedDetailRows = useMemo(() => {
    if (!selectedEntry || !selectedItem) return [];
    const rows: Array<{ label: string; value: string }> = [];
    if (selectedEntry.step) rows.push({ label: "Step", value: String(selectedEntry.step) });
    
    if (selectedItem.type === "computer_call") {
      const action = (selectedItem.action ?? {}) as Record<string, unknown>;
      Object.entries(action).forEach(([key, value]) => {
        if (key !== "type" && value) rows.push({ label: key, value: String(value) });
      });
    }
    
    if (selectedItem.type === "computer_call_output" && selectedOutput) {
      if (selectedOutput.url) rows.push({ label: "URL", value: String(selectedOutput.url) });
    }
    
    return rows;
  }, [selectedEntry, selectedItem, selectedOutput]);

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
        <ResizablePanel defaultSize={40} minSize={30}>
          <div className="h-full flex flex-col border-r border-white/10">
            <div className="p-4 border-b border-white/10 bg-white/5">
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">History</span>
            </div>
            <div className="flex-1 overflow-auto p-4 space-y-3" ref={scrollRef}>
                {timelineEntries.map((entry) => (
                  <button
                    key={entry.index}
                    onClick={() => setSelectedEntryIndex(entry.index)}
                    className={cn(
                      "w-full text-left p-3 rounded-2xl border transition-all duration-200 group relative",
                      selectedEntryIndex === entry.index
                        ? "bg-indigo-500/10 border-indigo-500/40 shadow-lg shadow-indigo-500/10"
                        : "bg-black/20 border-white/5 hover:border-white/20 hover:bg-white/5"
                    )}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] font-medium text-zinc-500 uppercase tracking-tight">Step {entry.step}</span>
                      <Badge variant="outline" className={cn("text-[9px] h-4 px-1.5 uppercase", timelineTone(entry.kind))}>
                        {entry.kind}
                      </Badge>
                    </div>
                    <div className="text-sm font-semibold text-zinc-100 group-hover:text-white transition-colors">
                      {entry.title}
                    </div>
                    {entry.subtitle && (
                      <div className="text-xs text-zinc-400 mt-1 line-clamp-2 leading-relaxed">
                        {entry.subtitle}
                      </div>
                    )}
                  </button>
                ))}
                {run.status === "running" && (
                   <div className="flex items-center gap-2 p-4 text-xs text-zinc-500 animate-pulse">
                     <Clock className="h-3 w-3" />
                     Waiting for next step...
                   </div>
                )}
              </div>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle className="bg-white/10" />

        {/* Right: Preview */}
        <ResizablePanel defaultSize={60} minSize={40}>
          <ScrollArea className="h-full bg-black/40">
            <div className="p-6 space-y-6">
              {selectedEntry ? (
                <>
                  <div className="space-y-4">
                     <div className="flex items-center justify-between">
                        <h3 className="text-lg font-semibold text-white">{selectedEntry.title}</h3>
                        {selectedScreenshot && (
                          <Button variant="ghost" size="sm" onClick={() => setIsFullscreenOpen(true)} className="h-8 text-indigo-400">
                             <Maximize2 className="h-4 w-4 mr-2" />
                             Fullscreen
                          </Button>
                        )}
                     </div>
                     
                     {selectedScreenshot ? (
                        <div 
                          className="relative rounded-2xl border border-white/10 bg-black overflow-hidden cursor-zoom-in group shadow-2xl"
                          onClick={() => setIsFullscreenOpen(true)}
                        >
                          <img
                            src={`data:image/png;base64,${selectedScreenshot}`}
                            alt="Screenshot"
                            className="w-full h-auto transition-transform duration-500 group-hover:scale-[1.01]"
                          />
                        </div>
                     ) : (
                        <div className="aspect-video rounded-2xl border border-dashed border-white/10 bg-white/5 flex items-center justify-center text-zinc-500 italic text-sm">
                          No screenshot for this step
                        </div>
                     )}
                  </div>

                  {selectedDetailRows.length > 0 && (
                    <div className="grid grid-cols-2 gap-3">
                       {selectedDetailRows.map((row) => (
                         <div key={row.label} className="p-3 rounded-xl bg-white/5 border border-white/5">
                            <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">{row.label}</div>
                            <div className="text-sm text-zinc-200 break-all">{row.value}</div>
                         </div>
                       ))}
                    </div>
                  )}

                  {run.status === "awaiting_ack" && selectedEntryIndex === latestOutputIndex && (
                    <Card className="border-amber-500/30 bg-amber-500/10 shadow-xl shadow-amber-900/20">
                      <CardContent className="p-6 space-y-4">
                        <div className="flex items-center gap-2 text-amber-200">
                          <AlertTriangle className="h-5 w-5" />
                          <h4 className="font-semibold">Approval Required</h4>
                        </div>
                        
                        {pendingChecks.length > 0 ? (
                           <div className="space-y-3">
                             {pendingChecks.map((check) => (
                               <div key={check.id} className="flex items-start gap-3 p-3 rounded-xl bg-black/30 border border-amber-500/20">
                                  <Checkbox 
                                    id={check.id} 
                                    checked={acknowledgedChecks.includes(check.id)}
                                    onCheckedChange={(checked) => toggleCheck(check.id, !!checked)}
                                    className="mt-1"
                                  />
                                  <div className="space-y-1">
                                    <div className="flex items-center gap-2">
                                      <Badge className={cn("text-[10px] h-4", severityTone(check.severity))}>{check.severity}</Badge>
                                      <span className="text-[10px] text-amber-200/60 uppercase tracking-widest">{check.category}</span>
                                    </div>
                                    <p className="text-sm text-zinc-200">{check.message}</p>
                                  </div>
                               </div>
                             ))}
                           </div>
                        ) : (
                           <p className="text-sm text-amber-200/80">Proceed with the next steps?</p>
                        )}

                        <div className="flex gap-3 pt-2">
                          <Button 
                            className="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white border-0 h-11" 
                            disabled={!ackReady || isActionPending}
                            onClick={() => onApprove(acknowledgedChecks)}
                          >
                            {isActionPending ? "Submitting..." : "Approve & Resume"}
                          </Button>
                          <Button 
                            variant="destructive" 
                            className="px-6 h-11"
                            disabled={isActionPending}
                            onClick={onDeny}
                          >
                            Deny
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </>
              ) : (
                <div className="h-full flex items-center justify-center text-zinc-500 italic">
                  Select a step to view details
                </div>
              )}
            </div>
          </ScrollArea>
        </ResizablePanel>
      </ResizablePanelGroup>

      <Dialog open={isFullscreenOpen} onOpenChange={setIsFullscreenOpen}>
        <DialogContent className="max-w-[95vw] w-full max-h-[95vh] h-full p-0 bg-black/95 border-white/10">
          <div className="w-full h-full flex items-center justify-center p-4 overflow-auto">
             <img
                src={`data:image/png;base64,${selectedScreenshot}`}
                alt="Fullscreen"
                className="max-w-none w-auto h-auto object-contain"
             />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
