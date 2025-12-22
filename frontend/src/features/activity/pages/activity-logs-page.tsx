import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  Activity as ActivityIcon,
  ArrowUpRight,
  GitPullRequest,
  History,
  Inbox,
  Server
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMergeRequests } from "@/features/mr/hooks/use-merge-requests";
import { useRequests } from "@/features/requests/hooks/use-requests";
import { useRuns } from "@/features/runs/hooks/use-runs";
import { useSandboxSessions } from "@/features/sandbox/hooks/use-sandbox-sessions";
import { useWorkspace } from "@/features/workspaces/workspace-context";
import { cn } from "@/lib/utils";

type ActivityEvent = {
  id: string;
  type: "Request" | "Run" | "Merge" | "Sandbox";
  title: string;
  description: string;
  timestamp: string;
  href?: string;
  icon: LucideIcon;
};

function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function getTone(type: ActivityEvent["type"]) {
  switch (type) {
    case "Request":
      return "bg-indigo-500/15 text-indigo-100 border-indigo-500/30";
    case "Run":
      return "bg-emerald-500/15 text-emerald-100 border-emerald-500/30";
    case "Merge":
      return "bg-amber-500/15 text-amber-100 border-amber-500/30";
    case "Sandbox":
    default:
      return "bg-sky-500/15 text-sky-100 border-sky-500/30";
  }
}

export default function ActivityLogsPage() {
  const queryClient = useQueryClient();
  const [selectedEvent, setSelectedEvent] = useState<ActivityEvent | null>(null);
  const { activeWorkspace } = useWorkspace();
  const workspaceUid = activeWorkspace?.uid;
  const { data: requests, isLoading: requestsLoading } = useRequests(workspaceUid);
  const { data: runs, isLoading: runsLoading } = useRuns();
  const { data: mergeRequests, isLoading: mergeRequestsLoading } = useMergeRequests();
  const { data: sandboxSessions, isLoading: sandboxSessionsLoading } = useSandboxSessions();

  const scopedRequestIds = useMemo(
    () => new Set((requests ?? []).map((request) => request.id)),
    [requests]
  );
  const scopedRuns = useMemo(
    () => (runs ?? []).filter((run) => scopedRequestIds.has(run.request_id)),
    [runs, scopedRequestIds]
  );
  const scopedMergeRequests = useMemo(
    () => (mergeRequests ?? []).filter((mr) => scopedRequestIds.has(mr.request_id)),
    [mergeRequests, scopedRequestIds]
  );

  const events = useMemo(() => {
    const items: ActivityEvent[] = [];

    (requests ?? []).forEach((request) => {
      if (!request.created_at) return;
      items.push({
        id: `request-${request.id}`,
        type: "Request",
        title: request.payload.title || "New automation request",
        description: request.project?.repository
          ? `Captured for ${request.project.repository}`
          : "Request captured in AstraForge.",
        timestamp: request.created_at,
        href: `/app/requests/${request.id}/run`,
        icon: Inbox
      });
    });

    (scopedRuns ?? []).forEach((run) => {
      const timestamp = run.started_at || run.finished_at;
      if (!timestamp) return;
      const status = run.status ? run.status.toLowerCase() : "queued";
      items.push({
        id: `run-${run.id}`,
        type: "Run",
        title: `Run ${status}`,
        description: run.request_title
          ? `Automation for “${run.request_title}”`
          : "Automation run kicked off.",
        timestamp,
        href: `/app/requests/${run.request_id}/run`,
        icon: ActivityIcon
      });
    });

    (scopedMergeRequests ?? []).forEach((mr) => {
      if (!mr.created_at) return;
      items.push({
        id: `merge-${mr.id}`,
        type: "Merge",
        title: mr.title || "Merge request opened",
        description: mr.target_branch
          ? `Targeting ${mr.target_branch}`
          : "Merge request created by AstraForge.",
        timestamp: mr.created_at,
        href: `/app/requests/${mr.request_id}/run`,
        icon: GitPullRequest
      });
    });

    (sandboxSessions ?? []).forEach((session) => {
      const timestamp = session.updated_at || session.created_at;
      if (!timestamp) return;
      items.push({
        id: `sandbox-${session.id}`,
        type: "Sandbox",
        title: `Sandbox ${session.status}`,
        description: `Mode: ${session.mode}`,
        timestamp,
        icon: Server
      });
    });

    return items
      .filter((item) => {
        const date = new Date(item.timestamp);
        return !Number.isNaN(date.getTime());
      })
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  }, [requests, sandboxSessions, scopedMergeRequests, scopedRuns]);

  const loading =
    requestsLoading || runsLoading || mergeRequestsLoading || sandboxSessionsLoading;

  useEffect(() => {
    if (events.length === 0) {
      setSelectedEvent(null);
      return;
    }
    if (!selectedEvent) {
      setSelectedEvent(events[0]);
      return;
    }
    const stillExists = events.find((event) => event.id === selectedEvent.id);
    if (!stillExists) {
      setSelectedEvent(events[0]);
    }
  }, [events, selectedEvent]);

  const summary = {
    total: events.length,
    requests: requests?.length ?? 0,
    runs: scopedRuns?.length ?? 0,
    merges: scopedMergeRequests?.length ?? 0,
    sandboxes: sandboxSessions?.length ?? 0
  };

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["requests"] });
    queryClient.invalidateQueries({ queryKey: ["runs"] });
    queryClient.invalidateQueries({ queryKey: ["merge-requests"] });
    queryClient.invalidateQueries({ queryKey: ["sandbox-sessions"] });
  };

  return (
    <div className="relative z-10 mx-auto w-full max-w-5xl space-y-8 px-4 py-8 text-zinc-100 sm:px-6 lg:px-10">
      <section className="home-card home-ring-soft space-y-4 rounded-3xl border border-white/10 bg-black/30 p-8 shadow-2xl shadow-indigo-500/15 backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-indigo-200/80">
              Observability
            </p>
            <h1 className="text-3xl font-semibold text-white">Activity logs</h1>
            <p className="max-w-2xl text-sm text-zinc-300">
              Follow every request, run, merge, and sandbox event streaming through AstraForge from a single timeline.
            </p>
          </div>
          <div className="flex flex-col gap-3 text-sm text-zinc-200">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-emerald-400" aria-hidden />
              <span className="text-xs uppercase tracking-[0.3em] text-emerald-100/80">
                Events tracked
              </span>
            </div>
            <p className="text-3xl font-semibold text-white">{summary.total}</p>
            <p className="text-xs text-zinc-400">Updated live from workspace activity</p>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-4">
          <Badge className="flex items-center justify-between gap-2 rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm text-white">
            <span className="uppercase tracking-[0.15em] text-xs text-indigo-100/80">
              Requests
            </span>
            <span className="text-base font-semibold">{summary.requests}</span>
          </Badge>
          <Badge className="flex items-center justify-between gap-2 rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm text-white">
            <span className="uppercase tracking-[0.15em] text-xs text-emerald-100/80">
              Runs
            </span>
            <span className="text-base font-semibold">{summary.runs}</span>
          </Badge>
          <Badge className="flex items-center justify-between gap-2 rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm text-white">
            <span className="uppercase tracking-[0.15em] text-xs text-amber-100/80">
              MRs
            </span>
            <span className="text-base font-semibold">{summary.merges}</span>
          </Badge>
          <Badge className="flex items-center justify-between gap-2 rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm text-white">
            <span className="uppercase tracking-[0.15em] text-xs text-sky-100/80">
              Sandboxes
            </span>
            <span className="text-base font-semibold">{summary.sandboxes}</span>
          </Badge>
        </div>
      </section>

      <Card className="home-card home-ring-soft rounded-3xl border border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
        <CardHeader className="flex flex-row items-start justify-between gap-4 border-b border-white/10">
          <div className="space-y-1">
            <CardTitle className="text-lg text-white">Timeline</CardTitle>
            <p className="text-sm text-zinc-300">
              Reverse-chronological feed of automation signals across the platform.
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="rounded-full px-4 text-zinc-200 hover:bg-white/10"
            onClick={handleRefresh}
          >
            Refresh
          </Button>
        </CardHeader>
        <CardContent className="p-6">
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, index) => (
                <div
                  key={index}
                  className="flex items-start gap-3 rounded-2xl border border-white/10 bg-white/5 p-4"
                >
                  <Skeleton className="h-10 w-10 rounded-xl" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-4 w-28" />
                    <Skeleton className="h-6 w-64" />
                    <Skeleton className="h-4 w-40" />
                  </div>
                </div>
              ))}
            </div>
          ) : events.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-white/15 bg-white/5 px-6 py-10 text-center">
              <History className="h-6 w-6 text-indigo-200" />
              <div className="space-y-1">
                <p className="text-base font-semibold text-white">No activity yet</p>
                <p className="text-sm text-zinc-400">
                  New requests, runs, merge requests, and sandbox events will show up here.
                </p>
              </div>
              <Button asChild variant="brand" size="sm" className="rounded-xl">
                <Link to="/app/requests">
                  <ArrowUpRight className="mr-2 h-4 w-4" />
                  Start a request
                </Link>
              </Button>
            </div>
          ) : (
            <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
              <div className="space-y-3">
                {events.map((event) => {
                  const Icon = event.icon;
                  const isSelected = selectedEvent?.id === event.id;
                  return (
                    <button
                      key={event.id}
                      type="button"
                      onClick={() => setSelectedEvent(event)}
                      className={cn(
                        "group relative flex w-full items-start gap-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70",
                        isSelected ? "border-white/30 bg-white/10 shadow-lg shadow-indigo-500/10" : "hover:border-white/25 hover:bg-white/10"
                      )}
                    >
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10 text-white ring-1 ring-white/10">
                        <Icon className="h-5 w-5" />
                      </div>
                      <div className="flex-1 min-w-0 space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge
                            className={cn(
                              "rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide",
                              getTone(event.type)
                            )}
                          >
                            {event.type}
                          </Badge>
                          <span className="text-xs text-zinc-400">
                            {formatTimestamp(event.timestamp)}
                          </span>
                        </div>
                        <p className="text-base font-semibold text-white">{event.title}</p>
                        <p className="text-sm text-zinc-300">{event.description}</p>
                        {event.href ? (
                          <span className="inline-flex items-center gap-1 text-sm font-medium text-indigo-200">
                            View details
                            <ArrowUpRight className="h-4 w-4" />
                          </span>
                        ) : null}
                      </div>
                    </button>
                  );
                })}
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
                {selectedEvent ? (
                  <div className="space-y-3">
                    <div className="flex items-center gap-3">
                      <selectedEvent.icon className="h-5 w-5 text-white" />
                      <Badge
                        className={cn(
                          "rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide",
                          getTone(selectedEvent.type)
                        )}
                      >
                        {selectedEvent.type}
                      </Badge>
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm uppercase tracking-[0.2em] text-zinc-400">When</p>
                      <p className="text-sm text-zinc-200">{formatTimestamp(selectedEvent.timestamp)}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm uppercase tracking-[0.2em] text-zinc-400">Title</p>
                      <p className="text-base font-semibold text-white">{selectedEvent.title}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm uppercase tracking-[0.2em] text-zinc-400">Details</p>
                      <p className="text-sm text-zinc-200">{selectedEvent.description}</p>
                    </div>
                    {selectedEvent.href ? (
                      <Button asChild size="sm" className="rounded-xl">
                        <Link to={selectedEvent.href}>
                          Open details
                          <ArrowUpRight className="ml-2 h-4 w-4" />
                        </Link>
                      </Button>
                    ) : (
                      <p className="text-xs text-zinc-400">
                        No linked detail view for this event type.
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="space-y-2 text-sm text-zinc-300">
                    <p>Select an activity to see more details.</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
