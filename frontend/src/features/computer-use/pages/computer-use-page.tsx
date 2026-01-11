import { useMemo, useState, useEffect } from "react";
import { Plus, LayoutGrid, CheckCircle2, ShieldAlert, MousePointerClick } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  useAcknowledgeComputerUseRun,
  useComputerUseRun,
  useComputerUseRuns,
  useComputerUseTimeline,
  useCreateComputerUseRun
} from "@/features/computer-use/hooks/use-computer-use";
import { type ComputerUseRun, type CreateComputerUseRunInput } from "@/lib/api-client";
import { ComputerUseSetup } from "../components/ComputerUseSetup";
import { ComputerUseRunView } from "../components/ComputerUseRunView";

function summarizeRuns(runs: ComputerUseRun[] | undefined) {
  const list = runs ?? [];
  let running = 0;
  let awaiting = 0;
  let completed = 0;
  list.forEach((run) => {
    const status = (run.status || "").toLowerCase();
    if (status.includes("running")) running += 1;
    if (status.includes("awaiting")) awaiting += 1;
    if (status.includes("completed")) completed += 1;
  });
  return {
    total: list.length,
    running,
    awaiting,
    completed
  };
}

export default function ComputerUsePage() {
  const [view, setView] = useState<"setup" | "run">("setup");
  const runsQuery = useComputerUseRuns();
  const runs = useMemo(() => runsQuery.data ?? [], [runsQuery.data]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const activeRun = useMemo(() => {
    return runs.find((run) => run.id === selectedRunId) ?? runs[0] ?? null;
  }, [runs, selectedRunId]);

  const runDetailQuery = useComputerUseRun(selectedRunId || activeRun?.id || null);
  const currentRun = runDetailQuery.data || activeRun;

  const timelineQuery = useComputerUseTimeline(currentRun?.id || null, {
    limit: 200,
    includeScreenshots: true,
    runStatus: currentRun?.status
  });

  const createRun = useCreateComputerUseRun();
  const acknowledgeRun = useAcknowledgeComputerUseRun();

  const summary = useMemo(() => summarizeRuns(runs), [runs]);

  useEffect(() => {
    if (view === "run" && !selectedRunId && currentRun) {
      setSelectedRunId(currentRun.id);
    }
  }, [view, selectedRunId, currentRun]);

  const handleStartRun = (payload: CreateComputerUseRunInput) => {
    createRun.mutate(payload, {
      onSuccess: (run) => {
        setSelectedRunId(run.id);
        setView("run");
        toast.success("Run started successfully");
      },
      onError: (error) => {
        toast.error(error instanceof Error ? error.message : "Failed to start run");
      }
    });
  };

  const handleApprove = (acknowledged: string[]) => {
    if (!currentRun) return;
    acknowledgeRun.mutate({
      id: currentRun.id,
      decision: "approve",
      acknowledged
    }, {
      onSuccess: () => toast.success("Run approved"),
      onError: (err) => toast.error(err.message)
    });
  };

  const handleDeny = () => {
    if (!currentRun) return;
    acknowledgeRun.mutate({
      id: currentRun.id,
      decision: "deny",
      acknowledged: []
    }, {
      onSuccess: () => toast.info("Run denied"),
      onError: (err) => toast.error(err.message)
    });
  };

  const handleExport = () => {
    if (!currentRun || !timelineQuery.data) return;
    const blob = new Blob([JSON.stringify(timelineQuery.data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `run-${currentRun.id}-timeline.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="relative z-10 mx-auto w-full max-w-[clamp(72rem,85vw,120rem)] space-y-8 px-4 py-8 text-zinc-100 sm:px-6 lg:px-10">
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div className="space-y-2">
           <div className="flex items-center gap-2 text-indigo-400 font-semibold uppercase tracking-[0.2em] text-[10px]">
             <LayoutGrid className="h-3 w-3" />
             Computer Use
           </div>
           <h1 className="text-4xl font-bold text-white tracking-tight">Browser Orchestration</h1>
           <p className="text-zinc-400 max-w-xl text-sm leading-relaxed">
             Execute and monitor safe browser runs with automated safety checks and full observability.
           </p>
        </div>

        <div className="flex items-center gap-4 bg-black/40 border border-white/10 rounded-2xl p-1 shadow-xl">
           <Button 
            variant={view === "setup" ? "secondary" : "ghost"} 
            onClick={() => setView("setup")}
            className="rounded-xl h-10 px-6 font-medium transition-all"
           >
             <Plus className="h-4 w-4 mr-2" />
             New Run
           </Button>
           <Button 
            variant={view === "run" ? "secondary" : "ghost"} 
            onClick={() => setView("run")}
            disabled={!currentRun}
            className="rounded-xl h-10 px-6 font-medium transition-all"
           >
             Live View
           </Button>
        </div>
      </header>

      {view === "setup" && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr,320px] gap-8 items-start">
           <ComputerUseSetup onSubmit={handleStartRun} isPending={createRun.isPending} />
           
           <div className="space-y-6">
              <div className="rounded-3xl border border-white/10 bg-black/30 p-6 space-y-4 backdrop-blur-md">
                 <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-500">System Status</h3>
                 <div className="space-y-3">
                    <div className="flex items-center justify-between p-3 rounded-2xl bg-white/5 border border-white/5">
                       <div className="flex items-center gap-2 text-xs text-zinc-400">
                         <MousePointerClick className="h-3.5 w-3.5" />
                         Active
                       </div>
                       <span className="text-lg font-bold text-white">{summary.running}</span>
                    </div>
                    <div className="flex items-center justify-between p-3 rounded-2xl bg-white/5 border border-white/5">
                       <div className="flex items-center gap-2 text-xs text-zinc-400">
                         <ShieldAlert className="h-3.5 w-3.5" />
                         Awaiting
                       </div>
                       <span className="text-lg font-bold text-amber-400">{summary.awaiting}</span>
                    </div>
                    <div className="flex items-center justify-between p-3 rounded-2xl bg-white/5 border border-white/5">
                       <div className="flex items-center gap-2 text-xs text-zinc-400">
                         <CheckCircle2 className="h-3.5 w-3.5" />
                         Completed
                       </div>
                       <span className="text-lg font-bold text-emerald-400">{summary.completed}</span>
                    </div>
                 </div>
              </div>

              {runs.length > 0 && (
                <div className="rounded-3xl border border-white/10 bg-black/30 p-6 space-y-4 backdrop-blur-md">
                   <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-500">Recent Runs</h3>
                   <div className="space-y-2 max-h-[400px] overflow-auto pr-2">
                      {runs.slice(0, 10).map((run) => (
                        <button
                          key={run.id}
                          onClick={() => {
                            setSelectedRunId(run.id);
                            setView("run");
                          }}
                          className="w-full text-left p-3 rounded-xl border border-white/5 bg-white/5 hover:bg-white/10 hover:border-white/20 transition-all group"
                        >
                           <div className="flex justify-between items-center mb-1">
                             <span className="text-[10px] font-mono text-zinc-500">{run.id.slice(0, 8)}</span>
                             <span className={run.status === "running" ? "text-indigo-400 animate-pulse" : "text-zinc-500"}>
                               <LayoutGrid className="h-3 w-3" />
                             </span>
                           </div>
                           <div className="text-xs font-medium text-zinc-200 line-clamp-2 group-hover:text-white">
                             {run.goal}
                           </div>
                        </button>
                      ))}
                   </div>
                </div>
              )}
           </div>
        </div>
      )}

      {view === "run" && currentRun && (
        <ComputerUseRunView
          run={currentRun}
          timelineItems={timelineQuery.data ?? []}
          onApprove={handleApprove}
          onDeny={handleDeny}
          isActionPending={acknowledgeRun.isPending}
          onExport={handleExport}
        />
      )}
      
      {view === "run" && !currentRun && (
        <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
           <div className="h-16 w-16 rounded-full bg-white/5 flex items-center justify-center border border-white/10">
              <LayoutGrid className="h-8 w-8 text-zinc-500" />
           </div>
           <div>
              <h3 className="text-xl font-semibold text-white">No active run selected</h3>
              <p className="text-zinc-400 text-sm">Start a new run or select one from history.</p>
           </div>
           <Button variant="outline" onClick={() => setView("setup")}>Return to Setup</Button>
        </div>
      )}
    </div>
  );
}
