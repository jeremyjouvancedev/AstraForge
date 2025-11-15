import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  GitBranch,
  Server,
} from "lucide-react";

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

interface DiffFileStat {
  path: string;
  additions: number;
  deletions: number;
}

function deriveDiffFiles(diffText: string | null | undefined): DiffFileStat[] {
  if (!diffText) return [];
  const files: DiffFileStat[] = [];
  const lines = diffText.split(/\r?\n/);
  let current: DiffFileStat | null = null;

  const pushCurrent = () => {
    if (current && current.path !== "/dev/null") {
      files.push(current);
    }
  };

  lines.forEach((line) => {
    if (line.startsWith("diff --git ")) {
      pushCurrent();
      const match = line.match(/^diff --git a\/(.+?) b\/(.+)$/);
      const path = match ? match[2] : line.replace("diff --git", "").trim();
      current = { path, additions: 0, deletions: 0 };
      return;
    }
    if (!current) return;
    if (line.startsWith("+++ ")) {
      if (line.startsWith("+++ b/")) {
        current.path = line.slice(6).trim();
      }
      return;
    }
    if (line.startsWith("--- ")) {
      return;
    }
    if (line.startsWith("+") && !line.startsWith("+++")) {
      current.additions += 1;
      return;
    }
    if (line.startsWith("-") && !line.startsWith("---")) {
      current.deletions += 1;
    }
  });

  pushCurrent();
  return files;
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
  const navigate = useNavigate();
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

  const requestPayload = (data?.payload ?? null) as Record<string, unknown> | null;
  const requestPrompt =
    typeof requestPayload?.["prompt"] === "string" ? (requestPayload["prompt"] as string) : null;
  const requestTitle =
    (typeof requestPayload?.["title"] === "string" ? (requestPayload["title"] as string) : null) ??
    "Request";
  const metadata = (data?.metadata ?? null) as Record<string, unknown> | null;
  const workspaceMeta = metadata && typeof metadata["workspace"] === "object" ? (metadata["workspace"] as Record<string, unknown>) : undefined;
  const repositorySlug = data?.project?.repository ?? "Unlinked repository";
  const baseBranch = workspaceMeta && typeof workspaceMeta["base_branch"] === "string" ? (workspaceMeta["base_branch"] as string) : undefined;
  const selectedArtifacts = selectedRun?.artifacts && typeof selectedRun.artifacts === "object" ? (selectedRun.artifacts as Record<string, unknown>) : undefined;
  const featureBranch = selectedArtifacts && typeof selectedArtifacts["branch"] === "string" ? (selectedArtifacts["branch"] as string) : undefined;
  const liveAssistantMessage = useMemo(() => {
    for (let i = selectedRunEvents.length - 1; i >= 0; i -= 1) {
      const event = selectedRunEvents[i];
      if (event?.type === "assistant_message" && typeof event.message === "string") {
        const createdAt =
          (typeof event["created_at"] === "string" ? (event["created_at"] as string) : null) ??
          selectedRun?.finished_at ??
          selectedRun?.started_at ??
          null;
        return { content: event.message, createdAt: createdAt ?? undefined };
      }
    }
    return null;
  }, [selectedRunEvents, selectedRun?.finished_at, selectedRun?.started_at]);

  const latestAssistantMessage = useMemo(() => {
    if (!selectedArtifacts) return null;
    const finalMessage = selectedArtifacts["final_message"];
    if (typeof finalMessage !== "string") return null;
    const trimmed = finalMessage.trim();
    if (!trimmed) return null;
    const createdAt = selectedRun?.finished_at ?? selectedRun?.started_at ?? undefined;
    return { content: trimmed, createdAt };
  }, [selectedArtifacts, selectedRun?.finished_at, selectedRun?.started_at]);
  const startedAtDate = selectedRun?.started_at ? new Date(selectedRun.started_at) : null;
  const finishedAtDate = selectedRun?.finished_at ? new Date(selectedRun.finished_at) : null;
  const durationSeconds = startedAtDate && finishedAtDate ? Math.max(0, Math.round((finishedAtDate.getTime() - startedAtDate.getTime()) / 1000)) : null;
  const formatTimestamp = (d: Date | null) => (d ? d.toLocaleString() : "Non demarre");
  const formatDuration = (s: number | null) => {
    if (s === null) return finishedAtDate ? "Moins d'une seconde" : "En cours";
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    const r = s % 60;
    return r === 0 ? `${m}m` : `${m}m ${r}s`;
  };
  const diffStats = summarizeDiff(selectedRun?.diff);
  const diffFiles = useMemo(() => deriveDiffFiles(selectedRun?.diff), [selectedRun?.diff]);
  const limitedDiffFiles = diffFiles.slice(0, 5);

  const [activePane, setActivePane] = useState<"log" | "diff">("log");
  useEffect(() => {
    const nextPane = selectedRun?.diff ? "diff" : "log";
    setActivePane((prev) => (prev === nextPane ? prev : nextPane));
  }, [selectedRunId, selectedRun?.diff]);

  const statusTone = (statusText: string | undefined) => {
    const s = (statusText ?? "").toLowerCase();
    if (s.includes("error") || s.includes("failed")) return { cls: "bg-destructive/10 text-destructive border-destructive/30", Icon: AlertTriangle } as const;
    if (s.includes("running") || s.includes("in_progress")) return { cls: "bg-blue-500/10 text-blue-400 border-blue-400/30", Icon: Clock } as const;
    if (s.includes("completed") || s.includes("done") || s.includes("success")) return { cls: "bg-green-500/10 text-green-400 border-green-400/30", Icon: CheckCircle2 } as const;
    return { cls: "bg-muted text-muted-foreground border-border/60", Icon: Clock } as const;
  };

  const RunHistoryRail = () => {
    if (combinedRuns.length === 0) {
      return (
        <div className="px-2 py-4 text-sm text-muted-foreground">No runs yet.</div>
      );
    }

    return (
      <ScrollArea className="w-full">
        <div className="flex w-max items-stretch gap-2 pr-4">
          {combinedRuns.map((run) => {
            const isSelected = run.id === selectedRunId;
            const runStarted = run.started_at && !Number.isNaN(Date.parse(run.started_at))
              ? new Date(run.started_at).toLocaleTimeString()
              : "Pending";
            const statusText = (run.status ?? "pending").replace(/_/g, " ");
            const { cls } = statusTone(run.status);

            return (
              <button
                type="button"
                key={run.id}
                onClick={() => setSelectedRunId(run.id)}
                className={cn(
                  "flex min-w-[180px] flex-col gap-1 rounded-2xl border px-3 py-2 text-left text-xs transition",
                  isSelected ? "border-primary bg-primary/10" : "border-border/60 hover:bg-muted/60",
                )}
                aria-current={isSelected ? "true" : undefined}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-semibold capitalize text-foreground">{statusText}</span>
                  <Badge variant="outline" className={cn("border px-2 py-0.5 text-[10px]", cls)}>{run.id.slice(0, 6)}</Badge>
                </div>
                <p className="text-muted-foreground">Started · {runStarted}</p>
              </button>
            );
          })}
        </div>
      </ScrollArea>
    );
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] min-h-0 flex-col overflow-hidden bg-muted/10">
      <header className="border-b border-border/60 bg-background/95">
        <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-4 lg:px-10">
          <div className="flex min-w-0 flex-1 items-center gap-4">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-9 rounded-full px-3 text-sm"
              onClick={() => navigate(-1)}
            >
              <ArrowLeft className="mr-2 h-4 w-4" /> Retour
            </Button>
            <div className="min-w-0 space-y-1">
              <p className="text-[10px] font-semibold uppercase tracking-[0.35em] text-muted-foreground">Demande</p>
              <h1 className="truncate text-2xl font-semibold text-foreground">{requestTitle}</h1>
              <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                <span className="flex min-w-0 items-center gap-1 text-foreground">
                  <Server className="h-4 w-4 opacity-70" />
                  <span className="truncate" title={repositorySlug}>{repositorySlug}</span>
                </span>
                <span className="flex min-w-0 items-center gap-1 text-foreground">
                  <GitBranch className="h-4 w-4 opacity-70" />
                  <span className="truncate" title={featureBranch ?? baseBranch ?? "Branch inconnue"}>
                    {featureBranch ?? baseBranch ?? "Branch inconnue"}
                  </span>
                </span>
                {selectedRunId ? (
                  <span className="font-mono text-xs text-muted-foreground">Run {selectedRunId.slice(0, 8)}</span>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                <span>Début {formatTimestamp(startedAtDate)}</span>
                <span>{selectedRun?.finished_at ? `Fin ${formatTimestamp(finishedAtDate)}` : "Toujours en cours"}</span>
                <span className="rounded-full border border-border/60 px-2 py-0.5 text-[11px] text-foreground">
                  Durée {formatDuration(durationSeconds)}
                </span>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" className="rounded-full px-4">Archiver</Button>
            <Button size="sm" variant="outline" className="rounded-full px-4">Partager</Button>
            <Button size="sm" className="rounded-full px-4">Voir l'extraction</Button>
          </div>
        </div>
      </header>

      <div className="flex flex-1 min-h-0 flex-col gap-6 px-4 pb-6 pt-4 lg:flex-row lg:px-10">
        <aside className="flex w-full min-w-0 flex-col lg:w-[38%]">
          <RunChatPanel
            requestId={requestId}
            history={historyJsonl}
            storedMessages={storedMessages}
            liveAssistantMessage={liveAssistantMessage}
            latestAssistantMessage={latestAssistantMessage}
            seedMessage={
              requestPrompt
                ? {
                    content: requestPrompt,
                    createdAt:
                      (typeof data?.created_at === "string" ? data.created_at : null) ??
                      selectedRun?.started_at ??
                      undefined,
                  }
                : undefined
            }
            className="flex-1"
          />
        </aside>

        <section className="flex w-full min-w-0 flex-1 flex-col gap-4 min-h-0">
          <Card className="flex flex-1 min-h-0 min-w-0 flex-col rounded-[32px] border border-border/70 bg-card shadow-sm">
            <Tabs
              value={activePane}
              onValueChange={(v) => setActivePane(v as "log" | "diff")}
              className="flex flex-1 min-h-0 flex-col"
            >
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/60 px-6 py-4">
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-[0.35em] text-muted-foreground">Vue detaillee</p>
                  <h2 className="truncate text-lg font-semibold text-foreground">{limitedDiffFiles[0]?.path ?? "Output preview"}</h2>
                  <p className="text-xs text-muted-foreground">
                    +{limitedDiffFiles[0]?.additions ?? diffStats.additions} / -{limitedDiffFiles[0]?.deletions ?? diffStats.deletions}
                  </p>
                </div>
                <TabsList className="rounded-full border border-border/60 bg-muted/30 p-1">
                  <TabsTrigger
                    value="diff"
                    className="rounded-full px-3 py-1 text-xs transition data-[state=active]:bg-primary/10 data-[state=active]:text-primary"
                  >
                    Diff
                  </TabsTrigger>
                  <TabsTrigger
                    value="log"
                    className="rounded-full px-3 py-1 text-xs transition data-[state=active]:bg-primary/10 data-[state=active]:text-primary"
                  >
                    Journaux
                  </TabsTrigger>
                </TabsList>
              </div>

              {combinedRuns.length > 1 ? (
                <div className="flex w-full flex-col gap-2 border-b border-border/60 bg-card/80 px-6 pb-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-muted-foreground">Autres executions</p>
                  <RunHistoryRail />
                </div>
              ) : null}

              <TabsContent
                value="diff"
                className="mt-0 flex flex-1 min-h-0 flex-col overflow-hidden px-6 py-5 data-[state=inactive]:hidden"
              >
                {selectedRun ? (
                  selectedRun.diff ? (
                    <div className="flex flex-1 min-h-0 overflow-hidden rounded-2xl border border-border/70 bg-background/90">
                      <DiffPreview
                        diff={selectedRun.diff}
                        className="flex-1 border-none"
                        maxHeight={560}
                      />
                    </div>
                  ) : (
                    <div className="rounded-2xl border border-border/70 bg-background/90 px-4 py-6 text-sm text-muted-foreground">
                      No diff captured for this run.
                    </div>
                  )
                ) : (
                  <div className="space-y-3">
                    <div className="h-10 w-1/3 animate-pulse rounded bg-muted" />
                    <div className="h-64 w-full animate-pulse rounded bg-muted" />
                  </div>
                )}
              </TabsContent>

              <TabsContent
                value="log"
                className="mt-0 flex flex-1 min-h-0 flex-col overflow-hidden px-6 py-5 data-[state=inactive]:hidden"
              >
                {selectedRun ? (
                  <div className="flex flex-1 min-h-0 overflow-hidden rounded-2xl border border-border/70 bg-background/90">
                    <RunLogViewer
                      events={selectedRunEvents}
                      className="flex-1 border-none"
                      fillHeight
                    />
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="h-10 w-1/3 animate-pulse rounded bg-muted" />
                    <div className="h-64 w-full animate-pulse rounded bg-muted" />
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </Card>

          {selectedRun && errorEvent && (
            <Card className="shrink-0 rounded-[32px] border border-destructive/40 bg-background shadow-sm">
              <div className="border-b border-destructive/30 px-6 py-3">
                <CardTitle className="flex items-center gap-2 text-sm font-semibold text-destructive">
                  <AlertTriangle className="h-4 w-4" /> Execution error
                </CardTitle>
              </div>
              <div className="px-6 py-4">
                <p className="whitespace-pre-wrap text-sm text-destructive/90">{errorEvent.message ?? "The run reported an error. Check the logs above for details."}</p>
              </div>
            </Card>
          )}
        </section>
      </div>
    </div>
  );
}
