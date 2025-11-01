import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
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

  const progress = useMemo(() => deriveProgress(events), [events]);
  const errorEvent = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i -= 1) {
      if (events[i]?.type === "error") {
        return events[i];
      }
    }
    return undefined;
  }, [events]);

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
          <Button asChild variant="outline" size="sm">
            <Link to={`/requests/${requestId}`}>Back to spec</Link>
          </Button>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(260px,320px)_minmax(0,1fr)]">
        <RunChatPanel
          requestId={requestId}
          className="min-h-[420px] lg:sticky lg:top-6 lg:h-[calc(100vh-12rem)]"
        />

        <div className="flex min-w-0 flex-col gap-6">
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

          <RunLogViewer events={events} className="border" />

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
