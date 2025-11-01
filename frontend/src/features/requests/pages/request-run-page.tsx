import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/cn";
import { useRequestDetail } from "@/features/requests/hooks/use-request-detail";
import {
  RunLogEvent,
  useRunLogStream,
} from "@/features/requests/hooks/use-run-log-stream";
import { RunLogViewer } from "@/features/requests/components/run-log-viewer";
import { RunChatPanel } from "@/features/requests/components/run-chat-panel";

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
}

function deriveProgress(events: RunLogEvent[]) {
  const results = STATUS_STAGES.map((status) => ({
    status,
    state: "pending" as "pending" | "active" | "done",
  }));

  let activeAssigned = false;
  results.forEach((item) => {
    const matched = events.find((event) => {
      if (event.stage && item.status.stages.includes(event.stage)) {
        return true;
      }
      if (item.status.types && event.type && item.status.types.includes(event.type)) {
        return true;
      }
      return false;
    });

    if (matched) {
      item.state = "done";
    } else if (!activeAssigned) {
      item.state = "active";
      activeAssigned = true;
    }
  });

  return results;
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
    if (!data?.metadata) {
      return [];
    }
    const rawRuns = data.metadata["runs"];
    if (!Array.isArray(rawRuns)) {
      return [];
    }
    return rawRuns
      .map((entry) => {
        if (!entry || typeof entry !== "object") {
          return null;
        }
        const record = entry as Record<string, unknown>;
        const id = typeof record["id"] === "string" ? (record["id"] as string) : null;
        if (!id) {
          return null;
        }
        const status =
          typeof record["status"] === "string"
            ? (record["status"] as string)
            : (typeof record["state"] === "string" ? (record["state"] as string) : undefined);
        const startedAt =
          typeof record["started_at"] === "string"
            ? (record["started_at"] as string)
            : (typeof record["started_at"] === "number"
                ? new Date(record["started_at"] as number).toISOString()
                : null);
        const finishedAt =
          typeof record["finished_at"] === "string"
            ? (record["finished_at"] as string)
            : (typeof record["finished_at"] === "number"
                ? new Date(record["finished_at"] as number).toISOString()
                : null);
        const eventsList = Array.isArray(record["events"])
          ? ((record["events"] as unknown[]).filter(
              (item) => item && typeof item === "object"
            ) as RunLogEvent[])
          : [];
        const artifacts =
          record["artifacts"] && typeof record["artifacts"] === "object"
            ? (record["artifacts"] as Record<string, unknown>)
            : undefined;
        const diff = typeof record["diff"] === "string" ? (record["diff"] as string) : null;
        const error = typeof record["error"] === "string" ? (record["error"] as string) : null;
        return {
          id,
          status,
          started_at: startedAt,
          finished_at: finishedAt,
          events: eventsList,
          diff,
          error,
          artifacts,
        };
      })
      .filter((value): value is StoredRunRecord => value !== null);
  }, [data?.metadata]);

  const liveRunIds = useMemo(() => {
    const ids = new Set<string>();
    events.forEach((eventItem) => {
      if (eventItem.run_id) {
        ids.add(eventItem.run_id);
      }
    });
    return ids;
  }, [events]);

  const combinedRuns = useMemo(() => {
    const runsMap = new Map<string, StoredRunRecord>();
    storedRuns.forEach((run) => {
      runsMap.set(run.id, run);
    });
    liveRunIds.forEach((runId) => {
      if (!runsMap.has(runId)) {
        runsMap.set(runId, {
          id: runId,
          status: "running",
          started_at: null,
          finished_at: null,
          events: [],
        });
      }
    });
    return Array.from(runsMap.values()).sort((a, b) => {
      const aTime = a.started_at ? new Date(a.started_at).getTime() : 0;
      const bTime = b.started_at ? new Date(b.started_at).getTime() : 0;
      if (aTime === bTime) {
        return b.id.localeCompare(a.id);
      }
      return bTime - aTime;
    });
  }, [storedRuns, liveRunIds]);

  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedRunId && combinedRuns.length > 0) {
      setSelectedRunId(combinedRuns[0].id);
    }
  }, [combinedRuns, selectedRunId]);

  const selectedRun = useMemo(
    () => combinedRuns.find((run) => run.id === selectedRunId) ?? null,
    [combinedRuns, selectedRunId]
  );

  const selectedRunEvents = useMemo(() => {
    const baseline =
      selectedRun?.events?.filter((event): event is RunLogEvent => Boolean(event)) ?? [];
    const liveEvents = events.filter(
      (event) => selectedRunId && event.run_id === selectedRunId
    );
    const dedupe = new Set<string>();
    const mergeOrder: RunLogEvent[] = [];
    [...baseline, ...liveEvents].forEach((event) => {
      const key = [
        event.run_id ?? "",
        event.type ?? "",
        event.stage ?? "",
        event.message ?? "",
        event.command ?? "",
        event.output ?? "",
        event.exit_code ?? "",
        event.cwd ?? "",
      ].join("|");
      if (dedupe.has(key)) {
        return;
      }
      dedupe.add(key);
      mergeOrder.push(event);
    });
    return mergeOrder;
  }, [selectedRun?.events, events, selectedRunId]);

  const errorEvent = useMemo(() => {
    for (let i = selectedRunEvents.length - 1; i >= 0; i -= 1) {
      if (selectedRunEvents[i]?.type === "error") {
        return selectedRunEvents[i];
      }
    }
    return undefined;
  }, [selectedRunEvents]);

  const progress = useMemo(() => deriveProgress(selectedRunEvents), [selectedRunEvents]);

  return (
    <div className="flex min-h-screen w-full flex-col gap-6 px-6 pb-10 pt-6 lg:px-10 lg:pb-12">
      <header className="space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm uppercase text-muted-foreground">Implementation run</p>
            <h1 className="text-2xl font-semibold">{data?.payload.title ?? "Request"}</h1>
            <p className="text-sm text-muted-foreground">
              Tracking execution progress for request {requestId}.
            </p>
          </div>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(260px,320px)_minmax(0,1fr)]">
        <RunChatPanel
          requestId={requestId}
          history={historyJsonl}
          storedMessages={storedMessages}
          className="min-h-[420px] lg:sticky lg:top-6 lg:h-[calc(100vh-12rem)]"
        />

        <div className="flex min-w-0 flex-col gap-6">
          <section className="space-y-3">
            <header className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold">Run History</h2>
                <p className="text-sm text-muted-foreground">
                  Select a run to view its log, diff, and status.
                </p>
              </div>
            </header>
            {combinedRuns.length === 0 ? (
              <Card>
                <CardContent className="p-4 text-sm text-muted-foreground">
                  No runs recorded yet. Trigger an execution to see progress here.
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {combinedRuns.map((run) => {
                  const isSelected = run.id === selectedRunId;
                  const statusLabel = run.status ?? "unknown";
                  const startedAt = run.started_at
                    ? new Date(run.started_at).toLocaleString()
                    : "Pending…";
                  const finishedAt = run.finished_at
                    ? new Date(run.finished_at).toLocaleString()
                    : undefined;
                  return (
                    <button
                      key={run.id}
                      type="button"
                      onClick={() => setSelectedRunId(run.id)}
                      className={cn(
                        "rounded-xl border px-4 py-3 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        isSelected
                          ? "border-primary bg-primary/10 text-primary-foreground"
                          : "border-border/60 hover:border-primary/40 hover:bg-primary/5"
                      )}
                    >
                      <p className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">
                        Run
                      </p>
                      <p className="truncate text-sm font-semibold text-foreground">
                        {statusLabel.replace(/_/g, " ").toUpperCase()}
                      </p>
                      <p className="mt-2 text-xs text-muted-foreground">Started: {startedAt}</p>
                      {finishedAt && (
                        <p className="text-xs text-muted-foreground/80">Finished: {finishedAt}</p>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">Progress</h2>
            <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950 shadow-lg">
              <div className="relative flex items-center gap-1 px-4 py-6">
                <div className="absolute left-10 right-10 top-1/2 h-px -translate-y-1/2 bg-gradient-to-r from-transparent via-zinc-800 to-transparent" />
                <ol className="relative z-10 flex w-full items-center justify-between gap-6">
                  {progress.map(({ status, state }) => (
                    <li
                      key={status.id}
                      className="flex w-full max-w-[10rem] flex-col items-center gap-2 text-center"
                    >
                      <div
                        className={cn(
                          "flex h-10 w-10 items-center justify-center rounded-full border text-xs font-semibold",
                          state === "done"
                            ? "border-green-500/60 bg-green-500/10 text-green-400 shadow-[0_0_20px_rgba(34,197,94,0.25)]"
                            : state === "active"
                            ? "border-blue-500/60 bg-blue-500/10 text-blue-300 shadow-[0_0_14px_rgba(59,130,246,0.25)] animate-pulse"
                            : "border-zinc-700 bg-zinc-900 text-zinc-500"
                        )}
                        aria-label={`${status.label} status ${state}`}
                      >
                        {status.label
                          .split(/\s+/)
                          .map((word) => word[0])
                          .join("")
                          .slice(0, 3)
                          .toUpperCase()}
                      </div>
                      <div className="space-y-1">
                        <p className="text-sm font-semibold text-zinc-100">{status.label}</p>
                        <p className="text-xs text-zinc-400">{status.description}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          </section>

          <RunLogViewer events={selectedRunEvents} className="border" />

          {errorEvent && (
            <Card className="border-destructive/40">
              <CardHeader>
                <CardTitle className="text-sm font-semibold text-destructive">
                  Execution error
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-destructive/90 whitespace-pre-wrap">
                  {errorEvent.message ?? "The run reported an error. Check the logs above for details."}
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
