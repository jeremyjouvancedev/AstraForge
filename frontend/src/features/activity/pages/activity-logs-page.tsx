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
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  activityEventsQueryKey,
  useActivityEvents
} from "@/features/activity/hooks/use-activity-events";
import { useWorkspace } from "@/features/workspaces/workspace-context";
import { useWorkspaceUsage } from "@/features/workspaces/hooks/use-workspace-usage";
import { cn } from "@/lib/utils";
import type { ActivityEventDto, WorkspaceUsageSummary } from "@/lib/api-client";

type ActivityEvent = {
  id: string;
  type: "Request" | "Run" | "Merge" | "Sandbox";
  title: string;
  description: string;
  timestamp: string;
  href?: string;
  icon: LucideIcon;
  consumption?: EventConsumption;
};

type EventConsumption =
  | {
      kind: "request";
      ordinal?: number;
    }
  | {
    kind: "sandbox";
    ordinal?: number;
    cpuSeconds?: number | null;
    storageBytes?: number | null;
  };

function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function formatOrdinal(value?: number) {
  if (!value || value <= 0) return null;
  const suffixes = ["th", "st", "nd", "rd"];
  const mod100 = value % 100;
  const suffix = suffixes[(value % 10 <= 3 && mod100 < 11) || mod100 > 13 ? value % 10 : 0] || "th";
  return `${value}${suffix}`;
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

function getIcon(type: ActivityEvent["type"]) {
  switch (type) {
    case "Request":
      return Inbox;
    case "Run":
      return ActivityIcon;
    case "Merge":
      return GitPullRequest;
    case "Sandbox":
    default:
      return Server;
  }
}

function mapConsumption(
  consumption?: ActivityEventDto["consumption"] | null
): EventConsumption | undefined {
  if (!consumption) return undefined;
  if (consumption.kind === "sandbox") {
    return {
      kind: "sandbox",
      ordinal: consumption.ordinal ?? undefined,
      cpuSeconds: consumption.cpu_seconds ?? null,
      storageBytes: consumption.storage_bytes ?? null
    };
  }
  return {
    kind: "request",
    ordinal: consumption.ordinal ?? undefined
  };
}

function EventConsumptionDetails({
  consumption,
  workspaceUsage
}: {
  consumption: EventConsumption;
  workspaceUsage: WorkspaceUsageSummary;
}) {
  const limits = workspaceUsage.limits;
  if (consumption.kind === "request") {
    const limitValue = limits.requests_per_month ?? null;
    const hasLimit = typeof limitValue === "number" && limitValue > 0;
    const ordinalLabel = formatOrdinal(consumption.ordinal);
    const progressValue =
      hasLimit && limitValue
        ? Math.min(((consumption.ordinal ?? 1) / limitValue) * 100, 100)
        : 0;
    return (
      <div className="space-y-2 text-xs text-zinc-300">
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[11px] font-semibold">
            <span className="text-zinc-200">Request quota</span>
            {hasLimit ? (
              <span className="text-zinc-400">
                {ordinalLabel ?? "1 request"} of {numberFormatter.format(limitValue ?? 0)}
              </span>
            ) : (
              <span className="text-zinc-400">Plan unlimited</span>
            )}
          </div>
          {hasLimit ? (
            <Progress value={progressValue} className="h-1.5 rounded-full bg-white/10" />
          ) : (
            <div className="h-1.5 rounded-full border border-dashed border-white/15" />
          )}
        </div>
        <p className="text-[11px] text-zinc-400">
          {ordinalLabel
            ? `This was your ${ordinalLabel} request this billing cycle.`
            : "Counts as one request on your plan."}
        </p>
      </div>
    );
  }

  const limitValue = limits.sandbox_sessions_per_month ?? null;
  const hasLimit = typeof limitValue === "number" && limitValue > 0;
  const ordinalLabel = formatOrdinal(consumption.ordinal);
  const progressValue =
    hasLimit && limitValue
      ? Math.min(((consumption.ordinal ?? 1) / limitValue) * 100, 100)
      : 0;
  const runtimeLabel = formatDuration(consumption.cpuSeconds);
  const storageLabel = formatBytes(consumption.storageBytes);

  return (
    <div className="space-y-2 text-xs text-zinc-300">
      <div className="space-y-1">
        <div className="flex items-center justify-between text-[11px] font-semibold">
          <span className="text-zinc-200">Sandbox sessions</span>
          {hasLimit ? (
            <span className="text-zinc-400">
              {ordinalLabel ?? "1 sandbox"} of {numberFormatter.format(limitValue ?? 0)}
            </span>
          ) : (
            <span className="text-zinc-400">Plan unlimited</span>
          )}
        </div>
        {hasLimit ? (
          <Progress value={progressValue} className="h-1.5 rounded-full bg-white/10" />
        ) : (
          <div className="h-1.5 rounded-full border border-dashed border-white/15" />
        )}
      </div>
      <div className="space-y-1 text-[11px] text-zinc-400">
        <p>
          {ordinalLabel
            ? `This was your ${ordinalLabel} sandbox session this cycle.`
            : "Counts as one sandbox session on your plan."}
        </p>
        <div className="flex flex-col gap-1 text-zinc-300">
          {runtimeLabel ? <span>Runtime: {runtimeLabel}</span> : null}
          {storageLabel ? <span>Storage written: {storageLabel}</span> : null}
        </div>
      </div>
    </div>
  );
}

function formatDuration(seconds?: number | null) {
  if (!seconds || seconds <= 0) return null;
  if (seconds < 60) return "<1 min";
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.max(1, Math.round(minutes))} min`;
  const hours = minutes / 60;
  if (hours < 24) {
    const rounded = hours >= 10 ? Math.round(hours) : hours.toFixed(1);
    return `${rounded} hr`;
  }
  const days = hours / 24;
  const rounded = days >= 10 ? Math.round(days) : days.toFixed(1);
  return `${rounded} d`;
}

function formatBytes(bytes?: number | null) {
  if (!bytes || bytes <= 0) return null;
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  const rounded = value >= 10 || index === 0 ? Math.round(value) : Number(value.toFixed(1));
  return `${rounded} ${units[index]}`;
}

const numberFormatter = new Intl.NumberFormat("en-US");

export default function ActivityLogsPage() {
  const queryClient = useQueryClient();
  const [selectedEvent, setSelectedEvent] = useState<ActivityEvent | null>(null);
  const { activeWorkspace } = useWorkspace();
  const workspaceUid = activeWorkspace?.uid;
  const {
    data: activityData,
    isLoading: activityLoading,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage
  } = useActivityEvents(workspaceUid);
  const {
    data: workspaceUsage,
    isLoading: workspaceUsageLoading,
    isError: workspaceUsageError
  } = useWorkspaceUsage(workspaceUid);

  const events = useMemo(() => {
    const pages = activityData?.pages ?? [];
    return pages.flatMap((page) =>
      page.results.map((event) => ({
        id: event.id,
        type: event.type,
        title: event.title,
        description: event.description,
        timestamp: event.timestamp,
        href: event.href ?? undefined,
        icon: getIcon(event.type),
        consumption: mapConsumption(event.consumption)
      }))
    );
  }, [activityData]);

  const loading = activityLoading || workspaceUsageLoading;

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

  const summary = activityData?.pages?.[0]?.summary ?? {
    total: activityData?.pages?.[0]?.count ?? events.length,
    requests: 0,
    runs: 0,
    merges: 0,
    sandboxes: 0
  };

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: activityEventsQueryKey(workspaceUid) });
    if (workspaceUid) {
      queryClient.invalidateQueries({ queryKey: ["workspace-usage", workspaceUid] });
    }
  };

  return (
    <div className="relative z-10 mx-auto flex h-full w-full max-w-[clamp(64rem,76vw,104rem)] flex-col gap-6 overflow-hidden px-4 py-6 text-zinc-100 sm:px-6 lg:px-10">
      <section className="home-card home-ring-soft shrink-0 space-y-4 rounded-3xl border border-white/10 bg-black/30 p-8 shadow-2xl shadow-indigo-500/15 backdrop-blur">
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

      <Card className="home-card home-ring-soft flex min-h-0 flex-1 flex-col rounded-3xl border border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
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
        <CardContent className="flex-1 min-h-0 p-6">
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
            <div className="grid h-full min-h-0 gap-4 lg:grid-cols-[2fr_1fr]">
              <div className="flex min-h-0 flex-col gap-3">
                <div className="flex-1 min-h-0 space-y-3 overflow-y-auto pr-1">
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
                  {hasNextPage ? (
                    <div className="flex justify-center pb-1 pt-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="rounded-xl border-white/20 text-zinc-100 hover:border-white/40 hover:text-white"
                        onClick={() => fetchNextPage()}
                        disabled={isFetchingNextPage}
                      >
                        {isFetchingNextPage ? "Loading..." : "Load more"}
                      </Button>
                    </div>
                  ) : null}
                </div>
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
                    <div className="space-y-2 pt-2">
                      <p className="text-xs font-semibold uppercase tracking-[0.3em] text-zinc-400">
                        Consumption
                      </p>
                      {workspaceUsageLoading ? (
                        <div className="space-y-1">
                          <Skeleton className="h-2 w-full rounded-full" />
                          <Skeleton className="h-2 w-3/4 rounded-full" />
                        </div>
                      ) : workspaceUsageError ? (
                        <p className="text-xs text-zinc-400">
                          Unable to load consumption data right now.
                        </p>
                      ) : selectedEvent.consumption && workspaceUsage ? (
                        <EventConsumptionDetails
                          consumption={selectedEvent.consumption}
                          workspaceUsage={workspaceUsage}
                        />
                      ) : (
                        <p className="text-xs text-zinc-400">No quota impact for this event.</p>
                      )}
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
