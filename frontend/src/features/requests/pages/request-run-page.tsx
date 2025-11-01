import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DiffPreview } from "@/components/diff-preview";
import { cn } from "@/lib/cn";
import { useRequestDetail } from "@/features/requests/hooks/use-request-detail";
import {
  RunLogEvent,
  useRunLogStream,
} from "@/features/requests/hooks/use-run-log-stream";
import { RunLogViewer } from "@/features/requests/components/run-log-viewer";
import { RunChatPanel } from "@/features/requests/components/run-chat-panel";
import {
  Clock,
  GitBranch,
  GitCommit,
  GitPullRequest,
  Server,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";

const STATUS_STAGES: Array<{
  id: string;
  label: string;
  description: string;
  stages: string[];
  types?: string[];
}> = [
  {
    id: "provisioning",
    label: "Spawning VM",
    description: "Allocating and connecting to the workspace provisioner.",
    stages: ["provisioning"],
  },
  {
    id: "setup",
    label: "Setup environment",
    description: "Preparing container runtime, proxies, and base tooling.",
    stages: ["workspace", "proxy"],
  },
  {
    id: "init",
    label: "Init script",
    description: "Cloning repository and uploading the generated specification.",
    stages: ["clone", "spec"],
    types: ["spec_ready"],
  },
  {
    id: "codex",
    label: "Codex output steps",
    description: "Codex CLI is applying the plan and streaming logs.",
    stages: ["codex"],
  },
  {
    id: "outputs",
    label: "Output script",
    description: "Gathering execution artifacts and computing diff report.",
    stages: ["diff"],
  },
  {
    id: "changes",
    label: "Changes",
    description: "Review generated changes, tests, and any merge request metadata.",
    stages: ["mr"],
    types: ["completed"],
  },
];

interface StoredRunRecord {
  id: string;
  status?: string;
  started_at?: string | null;
  finished_at?: string | null;
  events?: RunLogEvent[];
  diff?: string | null;
  error?: string | null;
  artifacts?: Record<string, unknown>;
  reports?: Record<string, unknown>;
}

function deriveProgress(events: RunLogEvent[]) {
  const results = STATUS_STAGES.map((status) => ({
    status,
    state: "pending" as "pending" | "active" | "done",
  }));
  let activeAssigned = false;
  results.forEach((item) => {
    const matched = events.find((event) => {
      if (event.stage && item.status.stages.includes(event.stage)) return true;
      if (item.status.types && event.type && item.status.types.includes(event.type)) return true;
      return false;
    });
    if (matched) item.state = "done";
    else if (!activeAssigned) { item.state = "active"; activeAssigned = true; }
  });
  return results;
}

function summarizeDiff(diffText: string | null | undefined) {
  if (!diffText) return { files: 0, additions: 0, deletions: 0 };
  const lines = diffText.split(/\r?\n/);
  let files = 0, additions = 0, deletions = 0;
  lines.forEach((line) => {
    if (line.startsWith("diff --git")) { files += 1; return; }
    if (line.startsWith("+++ ") || line.startsWith("--- ")) return;
    if (line.startsWith("+")) { additions += 1; return; }
    if (line.startsWith("-")) deletions += 1;
  });
  return { files, additions, deletions };
}

export default function RequestRunPage() {
  const params = useParams<{ id: string }>();
  const requestId = params.id ?? "";
  const { data } = useRequestDetail(requestId);
  const { events } = useRunLogStream(requestId, { enabled: Boolean(requestId) });
  const historyJsonl =
    data?.metadata && typeof data.metadata["history_jsonl"] === "string"
      ? (data.metadata["history_jsonl"] as string)
      : null;
  const storedMessages =
    data?.metadata && Array.isArray(data.metadata["chat_messages"])
      ? (data.metadata["chat_messages"] as Array<Record<string, unknown>>)
      : null;

  const storedRuns: StoredRunRecord[] = useMemo(() => {
    if (!data?.metadata) return [];
    const rawRuns = data.metadata["runs"];
    if (!Array.isArray(rawRuns)) return [];
    return rawRuns
      .map((entry) => {
        if (!entry || typeof entry !== "object") return null;
        const record = entry as Record<string, unknown>;
        const id = typeof record["id"] === "string" ? (record["id"] as string) : null;
        if (!id) return null;
        const status = typeof record["status"] === "string" ? (record["status"] as string)
          : (typeof record["state"] === "string" ? (record["state"] as string) : undefined);
        const startedAt = typeof record["started_at"] === "string" ? (record["started_at"] as string)
          : (typeof record["started_at"] === "number" ? new Date(record["started_at"] as number).toISOString() : null);
        const finishedAt = typeof record["finished_at"] === "string" ? (record["finished_at"] as string)
          : (typeof record["finished_at"] === "number" ? new Date(record["finished_at"] as number).toISOString() : null);
        const eventsList = Array.isArray(record["events"]) ? ((record["events"] as unknown[]).filter((item) => item && typeof item === "object") as RunLogEvent[]) : [];
        const artifacts = record["artifacts"] && typeof record["artifacts"] === "object" ? (record["artifacts"] as Record<string, unknown>) : undefined;
        const diff = typeof record["diff"] === "string" ? (record["diff"] as string) : null;
        const error = typeof record["error"] === "string" ? (record["error"] as string) : null;
        const reports = record["reports"] && typeof record["reports"] === "object" ? (record["reports"] as Record<string, unknown>) : undefined;
        return { id, status, started_at: startedAt, finished_at: finishedAt, events: eventsList, diff, error, artifacts, reports };
      })
      .filter((v): v is StoredRunRecord => v !== null);
  }, [data?.metadata]);

  const liveRunIds = useMemo(() => {
    const ids = new Set<string>();
    events.forEach((e) => { if (e.run_id) ids.add(e.run_id); });
    return ids;
  }, [events]);

  const combinedRuns = useMemo(() => {
    const runsMap = new Map<string, StoredRunRecord>();
    storedRuns.forEach((run) => { runsMap.set(run.id, run); });
    liveRunIds.forEach((runId) => {
      if (!runsMap.has(runId)) runsMap.set(runId, { id: runId, status: "running", started_at: null, finished_at: null, events: [] });
    });
    return Array.from(runsMap.values()).sort((a, b) => {
      const aTime = a.started_at ? new Date(a.started_at).getTime() : 0;
      const bTime = b.started_at ? new Date(b.started_at).getTime() : 0;
      if (aTime === bTime) return b.id.localeCompare(a.id);
      return bTime - aTime;
    });
  }, [storedRuns, liveRunIds]);

  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  useEffect(() => { if (!selectedRunId && combinedRuns.length > 0) setSelectedRunId(combinedRuns[0].id); }, [combinedRuns, selectedRunId]);

  const selectedRun = useMemo(() => combinedRuns.find((run) => run.id === selectedRunId) ?? null, [combinedRuns, selectedRunId]);

  const selectedRunEvents = useMemo(() => {
    const baseline = selectedRun?.events?.filter((e): e is RunLogEvent => Boolean(e)) ?? [];
    const liveEvents = events.filter((e) => selectedRunId && e.run_id === selectedRunId);
    const dedupe = new Set<string>();
    const merge: RunLogEvent[] = [];
    [...baseline, ...liveEvents].forEach((e) => {
      const key = [e.run_id ?? "", e.type ?? "", e.stage ?? "", e.message ?? "", e.command ?? "", e.output ?? "", e.exit_code ?? "", e.cwd ?? ""].join("|");
      if (!dedupe.has(key)) { dedupe.add(key); merge.push(e); }
    });
    return merge;
  }, [selectedRun?.events, events, selectedRunId]);

  const errorEvent = useMemo(() => {
    for (let i = selectedRunEvents.length - 1; i >= 0; i -= 1) {
      if (selectedRunEvents[i]?.type === "error") return selectedRunEvents[i];
    }
    return undefined;
  }, [selectedRunEvents]);

  const progress = useMemo(() => deriveProgress(selectedRunEvents), [selectedRunEvents]);
  const metadata = (data?.metadata ?? null) as Record<string, unknown> | null;
  const workspaceMeta = metadata && typeof metadata["workspace"] === "object" ? (metadata["workspace"] as Record<string, unknown>) : undefined;
  const repositorySlug = data?.project?.repository ?? "Unlinked repository";
  const baseBranch = workspaceMeta && typeof workspaceMeta["base_branch"] === "string" ? (workspaceMeta["base_branch"] as string) : undefined;
  const selectedArtifacts = selectedRun?.artifacts && typeof selectedRun.artifacts === "object" ? (selectedRun.artifacts as Record<string, unknown>) : undefined;
  const featureBranch = selectedArtifacts && typeof selectedArtifacts["branch"] === "string" ? (selectedArtifacts["branch"] as string) : undefined;
  const commitHash = selectedArtifacts && typeof selectedArtifacts["commit"] === "string" ? (selectedArtifacts["commit"] as string) : undefined;
  const startedAtDate = selectedRun?.started_at ? new Date(selectedRun.started_at) : null;
  const finishedAtDate = selectedRun?.finished_at ? new Date(selectedRun.finished_at) : null;
  const durationSeconds = startedAtDate && finishedAtDate ? Math.max(0, Math.round((finishedAtDate.getTime() - startedAtDate.getTime()) / 1000)) : null;
  const formatTimestamp = (d: Date | null) => (d ? d.toLocaleString() : "Not started");
  const formatDuration = (s: number | null) => {
    if (s === null) return finishedAtDate ? "Under a second" : "In progress…";
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60); const r = s % 60; return r === 0 ? `${m}m` : `${m}m ${r}s`;
  };
  const runStatusLabel = (selectedRun?.status ?? "pending").replace(/_/g, " ");
  const diffStats = summarizeDiff(selectedRun?.diff);

  const [activePane, setActivePane] = useState<"log" | "diff">("log");
  useEffect(() => { setActivePane("log"); }, [selectedRunId]);

  const statusTone = (statusText: string | undefined) => {
    const s = (statusText ?? "").toLowerCase();
    if (s.includes("error") || s.includes("failed")) return { cls: "bg-destructive/10 text-destructive border-destructive/30", Icon: AlertTriangle } as const;
    if (s.includes("running") || s.includes("in_progress")) return { cls: "bg-blue-500/10 text-blue-400 border-blue-400/30", Icon: Clock } as const;
    if (s.includes("completed") || s.includes("done") || s.includes("success")) return { cls: "bg-green-500/10 text-green-400 border-green-400/30", Icon: CheckCircle2 } as const;
    return { cls: "bg-muted text-muted-foreground border-border/60", Icon: Clock } as const;
  };

  const RequestSummaryCard = () => (
    <Card className="rounded-2xl border border-border/70 bg-background shadow-sm">
      <CardHeader className="space-y-2 pb-3">
        <div className="text-[10px] font-semibold uppercase tracking-[0.35em] text-muted-foreground">Request</div>
        <CardTitle className="text-lg">{data?.payload.title ?? "Request"}</CardTitle>
        <p className="text-xs text-muted-foreground">{repositorySlug}{baseBranch ? ` · Base ${baseBranch}` : ""}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">Execution</p>
          <div className="flex flex-wrap items-center gap-2">
            {(() => { const { cls, Icon } = statusTone(selectedRun?.status); return (
              <Badge variant="outline" className={cn("border px-2.5 py-1 text-xs", cls)}>
                <Icon className="mr-1.5 h-3.5 w-3.5" />
                <span className="capitalize">{runStatusLabel}</span>
              </Badge>
            );})()}
            <Badge variant="secondary" className="rounded-full px-2.5 py-1 text-[11px]"><Clock className="mr-1 h-3 w-3" /> {formatDuration(durationSeconds)}</Badge>
          </div>
        </div>
        <Separator />
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">Summary</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            <li>No summary available for this run.</li>
          </ul>
        </div>
        <Separator />
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">Testing</p>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Badge variant="outline" className="border-border/60">pytest</Badge>
            <span>—</span>
          </div>
        </div>
        <Separator />
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">Files</p>
          <div className="rounded-lg border border-border/70 bg-muted/30 p-3 text-sm">
            <div className="flex items-center justify-between">
              <span>Changed files</span>
              <Badge variant="secondary">{diffStats.files}</Badge>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">+{diffStats.additions} / -{diffStats.deletions}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );

  const RunOverviewCard = () => (
    <Card className="rounded-2xl border border-border/70 bg-background shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base"><Server className="h-4 w-4" /> Run Overview</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">Repository</p>
            <p>{repositorySlug}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">Base</p>
            <p className="font-mono text-xs">{baseBranch ?? "—"}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">Feature</p>
            <p className="flex items-center gap-1 font-mono text-xs"><GitBranch className="h-3 w-3 opacity-70" />{featureBranch ?? "—"}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">Commit</p>
            <p className="flex items-center gap-1 font-mono text-xs"><GitCommit className="h-3 w-3 opacity-70" />{commitHash ? commitHash.slice(0,12) : "—"}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">Started</p>
            <p>{formatTimestamp(startedAtDate)}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">Finished</p>
            <p>{selectedRun?.finished_at ? formatTimestamp(finishedAtDate) : "In progress…"}</p>
          </div>
        </div>
        <Separator />
        <div className="flex items-center justify-between">
          <Badge variant="outline" className="rounded-full px-2.5 py-1 text-[10px]"><GitPullRequest className="mr-1 h-3 w-3" /> PR</Badge>
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs">Archive</Button>
            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs">Share</Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );

  const RunHistoryCard = ({ className }: { className?: string }) => (
    <Card className={cn("rounded-2xl border border-border/70 bg-background shadow-sm", className)}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Run History</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {combinedRuns.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-muted-foreground">No runs yet.</div>
        ) : (
          <ScrollArea className="max-h-[24rem]">
            <ul className="divide-y divide-border/60">
              {combinedRuns.map((run) => {
                const isSelected = run.id === selectedRunId;
                const runStarted = run.started_at && !Number.isNaN(Date.parse(run.started_at)) ? new Date(run.started_at).toLocaleString() : "Pending…";
                const runFinished = run.finished_at && !Number.isNaN(Date.parse(run.finished_at)) ? new Date(run.finished_at).toLocaleString() : null;
                const statusText = (run.status ?? "pending").replace(/_/g, " ");
                const { cls } = statusTone(run.status);
                return (
                  <li key={run.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedRunId(run.id)}
                      className={cn("flex w-full items-start justify-between gap-3 px-4 py-3 text-left transition", isSelected ? "bg-primary/10" : "hover:bg-muted/60")}
                      aria-current={isSelected ? "true" : undefined}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate text-sm font-semibold capitalize text-foreground">{statusText}</span>
                          <Badge variant="outline" className={cn("border px-2 py-0.5 text-[10px]", cls)}>{run.id.slice(0, 6)}</Badge>
                        </div>
                        <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">Started: {runStarted}{runFinished ? ` · Finished: ${runFinished}` : ""}</p>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );

  return (
    <div className="mx-auto flex h-[calc(100vh-4rem)] w-full gap-6 px-4 pb-8 pt-6 lg:px-8">
      <aside className="flex h-full w-full flex-col overflow-hidden lg:w-1/3">
        <RunChatPanel requestId={requestId} history={historyJsonl} storedMessages={storedMessages} className="flex-1" />
      </aside>

      <main className="flex h-full w-full flex-1 flex-col gap-6 overflow-hidden lg:w-2/3">
        <div className="grid shrink-0 gap-4 md:grid-cols-3">
          <div className="md:col-span-1">
            <RequestSummaryCard />
          </div>
          <div className="md:col-span-1">
            <RunOverviewCard />
          </div>
          <div className="md:col-span-1">
            <RunHistoryCard className="h-full min-h-[14rem]" />
          </div>
        </div>

        <Card className="flex min-h-0 flex-1 flex-col rounded-2xl border border-border/70 bg-background shadow-sm">
          <CardHeader className="gap-4 pb-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.35em] text-muted-foreground">Request Execution</p>
                <h1 className="text-2xl font-semibold text-foreground">{data?.payload.title ?? "Request"}</h1>
                <p className="text-sm text-muted-foreground">{repositorySlug}{baseBranch ? ` · Base ${baseBranch}` : ""}</p>
              </div>
              <Badge variant="secondary" className="rounded-full px-3 py-1 text-xs"><Clock className="mr-1.5 h-3.5 w-3.5" /> {formatDuration(durationSeconds)}</Badge>
            </div>
            <Separator />

            <div className="overflow-hidden rounded-xl border border-border/70 bg-muted/20">
              <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-5">
                {progress.map(({ status, state }) => (
                  <div key={status.id} className="flex min-w-[120px] flex-col items-center gap-2 text-center">
                    <div className={cn(
                      "flex h-10 w-10 items-center justify-center rounded-full border text-xs font-semibold",
                      state === "done"
                        ? "border-green-500/60 bg-green-500/10 text-green-500"
                        : state === "active"
                        ? "border-primary/60 bg-primary/10 text-primary"
                        : "border-border/70 bg-muted text-muted-foreground"
                    )}>
                      {status.label.split(/\s+/).map((w) => w[0]).join("").slice(0,3).toUpperCase()}
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm font-semibold text-foreground">{status.label}</p>
                      <p className="text-xs text-muted-foreground">{status.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </CardHeader>

          <CardContent className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <Tabs value={activePane} onValueChange={(v) => setActivePane(v as "log" | "diff")} className="flex min-h-0 flex-1 flex-col">
              <div className="mb-4 flex shrink-0 items-center justify-between">
                <TabsList className="rounded-full border border-border/60 bg-muted/30 p-1">
                  <TabsTrigger
                    value="log"
                    className="rounded-full px-3 py-1 text-xs transition data-[state=active]:bg-primary/10 data-[state=active]:text-primary"
                  >
                    Journaux
                  </TabsTrigger>
                  <TabsTrigger
                    value="diff"
                    className="rounded-full px-3 py-1 text-xs transition data-[state=active]:bg-primary/10 data-[state=active]:text-primary"
                  >
                    Diff
                  </TabsTrigger>
                </TabsList>
              </div>

              <TabsContent value="log" className="flex min-h-0 flex-1 flex-col">
                {selectedRun ? (
                  <div className="flex min-h-0 flex-1 overflow-hidden rounded-2xl border border-border/70 bg-background/90">
                    <RunLogViewer events={selectedRunEvents} className="flex-1 border-none" fillHeight />
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="h-10 w-1/3 animate-pulse rounded bg-muted" />
                    <div className="h-64 w-full animate-pulse rounded bg-muted" />
                  </div>
                )}
              </TabsContent>

              <TabsContent value="diff" className="flex min-h-0 flex-1 flex-col">
                {selectedRun ? (
                  selectedRun.diff ? (
                    <div className="flex min-h-0 flex-1 overflow-hidden rounded-2xl border border-border/70 bg-background/90">
                      <DiffPreview diff={selectedRun.diff} className="flex-1 border-none" maxHeight={560} />
                    </div>
                  ) : (
                    <div className="rounded-2xl border border-border/70 bg-background/90 px-4 py-6 text-sm text-muted-foreground">No diff captured for this run.</div>
                  )
                ) : (
                  <div className="space-y-3">
                    <div className="h-10 w-1/3 animate-pulse rounded bg-muted" />
                    <div className="h-64 w-full animate-pulse rounded bg-muted" />
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        {selectedRun && errorEvent && (
          <Card className="shrink-0 rounded-2xl border border-destructive/40 bg-background shadow-sm">
            <CardHeader className="border-b border-destructive/30 pb-3">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold text-destructive">
                <AlertTriangle className="h-4 w-4" /> Execution error
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="whitespace-pre-wrap text-sm text-destructive/90">{errorEvent.message ?? "The run reported an error. Check the logs above for details."}</p>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
