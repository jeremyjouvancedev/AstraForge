import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useRequestDetail } from "@/features/requests/hooks/use-request-detail";
import {
  RunLogEvent,
  useRunLogStream,
} from "@/features/requests/hooks/use-run-log-stream";
import { RunLogViewer } from "@/features/requests/components/run-log-viewer";

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
    <div className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
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

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold uppercase tracking-wide">
            Status overview
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-4">
            {progress.map(({ status, state }) => (
              <li
                key={status.id}
                className="rounded border border-border/60 p-4"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold text-foreground">{status.label}</p>
                    <p className="text-sm text-muted-foreground">{status.description}</p>
                  </div>
                  <span
                    className={
                      state === "done"
                        ? "rounded-full bg-green-500/15 px-3 py-1 text-xs font-semibold text-green-600"
                        : state === "active"
                        ? "rounded-full bg-blue-500/10 px-3 py-1 text-xs font-semibold text-blue-600"
                        : "rounded-full bg-muted px-3 py-1 text-xs font-semibold text-muted-foreground"
                    }
                  >
                    {state === "done" ? "Done" : state === "active" ? "In progress" : "Pending"}
                  </span>
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

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
  );
}
