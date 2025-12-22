import { type ComponentType, useMemo } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  BadgeCheck,
  BarChart2,
  Layers,
  PlayCircle,
  Server
} from "lucide-react";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent
} from "@/components/ui/chart";
import { Skeleton } from "@/components/ui/skeleton";
import { useMergeRequests } from "@/features/mr/hooks/use-merge-requests";
import { useRepositoryLinks } from "@/features/repositories/hooks/use-repository-links";
import { useRequests } from "@/features/requests/hooks/use-requests";
import { useRuns } from "@/features/runs/hooks/use-runs";
import { useSandboxSessions } from "@/features/sandbox/hooks/use-sandbox-sessions";
import { useWorkspace } from "@/features/workspaces/workspace-context";

type MetricCardProps = {
  label: string;
  value: string | number;
  helper?: string;
  icon: ComponentType<{ className?: string }>;
  loading?: boolean;
};

function toLower(value: string | undefined | null) {
  return (value || "").toLowerCase();
}

function MetricCard({ label, value, helper, icon: Icon, loading }: MetricCardProps) {
  return (
    <Card className="home-card home-ring-soft rounded-2xl border border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
      <CardContent className="flex items-start gap-4 p-5">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-indigo-500/10 text-indigo-200 ring-1 ring-indigo-400/20">
          <Icon className="h-5 w-5" />
        </div>
        <div className="flex flex-col">
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-indigo-100/80">
            {label}
          </p>
          {loading ? (
            <div className="mt-3 space-y-2">
              <Skeleton className="h-7 w-20" />
              <Skeleton className="h-4 w-36" />
            </div>
          ) : (
            <>
              <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
              {helper && <p className="text-sm text-zinc-300">{helper}</p>}
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default function AppOverviewPage() {
  const { activeWorkspace, loading: workspaceLoading } = useWorkspace();
  const workspaceUid = activeWorkspace?.uid;
  const { data: requests, isLoading: requestsLoading } = useRequests(workspaceUid);
  const { data: runs, isLoading: runsLoading } = useRuns();
  const {
    data: mergeRequests,
    isLoading: mergeRequestsLoading
  } = useMergeRequests();
  const {
    data: repositoryLinks,
    isLoading: repositoryLinksLoading
  } = useRepositoryLinks(workspaceUid);
  const repoLinksLoading = workspaceLoading || repositoryLinksLoading || !workspaceUid;
  const {
    data: sandboxSessions,
    isLoading: sandboxSessionsLoading
  } = useSandboxSessions();

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

  const requestStats = useMemo(() => {
    const list = requests ?? [];
    const sorted = list
      .slice()
      .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
    let active = 0;
    let completed = 0;
    list.forEach((request) => {
      const state = toLower(request.state);
      const isDone = state.includes("done") || state.includes("complete");
      const isFailed = state.includes("fail");
      if (isDone) completed += 1;
      if (!isDone && !isFailed) active += 1;
    });
    return {
      total: list.length,
      active,
      completed,
      latestTitle: sorted[0]?.payload.title ?? null
    };
  }, [requests]);

  const runStats = useMemo(() => {
    const list = scopedRuns ?? [];
    const successful = list.filter((run) => {
      const status = toLower(run.status);
      return (
        status.includes("done") ||
        status.includes("complete") ||
        status.includes("success")
      );
    }).length;
    return { total: list.length, successful };
  }, [scopedRuns]);

  const mergeStats = useMemo(() => {
    const list = scopedMergeRequests ?? [];
    const open = list.filter((mr) => {
      const status = toLower(mr.status);
      return status.includes("open") || status.includes("draft");
    }).length;
    return { total: list.length, open };
  }, [scopedMergeRequests]);

  const sandboxStats = useMemo(() => {
    const list = sandboxSessions ?? [];
    let ready = 0;
    let starting = 0;
    let failed = 0;
    let terminated = 0;
    const modeCounts: Record<string, number> = {};
    list.forEach((session) => {
      const status = toLower(session.status);
      if (status.includes("ready")) ready += 1;
      else if (status.includes("start")) starting += 1;
      else if (status.includes("fail")) failed += 1;
      else if (status.includes("terminate")) terminated += 1;
      modeCounts[session.mode] = (modeCounts[session.mode] || 0) + 1;
    });
    return {
      total: list.length,
      ready,
      starting,
      failed,
      terminated,
      modes: modeCounts
    };
  }, [sandboxSessions]);

  const sandboxChartData = useMemo(() => {
    const list = sandboxSessions ?? [];
    const countsByDate: Record<string, number> = {};
    list.forEach((session) => {
      if (!session.created_at) return;
      const date = new Date(session.created_at);
      if (Number.isNaN(date.getTime())) return;
      const key = date.toISOString().slice(0, 10);
      countsByDate[key] = (countsByDate[key] || 0) + 1;
    });
    const today = new Date();
    const days = Array.from({ length: 7 }).map((_, idx) => {
      const day = new Date(today);
      day.setDate(today.getDate() - (6 - idx));
      const key = day.toISOString().slice(0, 10);
      const label = day.toLocaleDateString(undefined, { month: "short", day: "numeric" });
      return {
        key,
        label,
        count: countsByDate[key] || 0
      };
    });
    return days;
  }, [sandboxSessions]);

  const sandboxChartConfig = {
    sandboxes: {
      label: "Sandboxes",
      color: "hsl(222, 83%, 58%)"
    }
  };

  const repoCount = repositoryLinks?.length ?? 0;
  const highlightedRequests = useMemo(() => {
    const list = requests ?? [];
    return list
      .slice()
      .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))
      .slice(0, 4);
  }, [requests]);

  const anyLoading =
    requestsLoading ||
    runsLoading ||
    mergeRequestsLoading ||
    repoLinksLoading ||
    sandboxSessionsLoading;

  return (
    <div className="relative z-10 mx-auto w-full max-w-6xl space-y-8 px-4 py-8 text-zinc-100 sm:px-6 lg:px-10">
      <section className="home-card home-ring-soft flex flex-col gap-6 rounded-3xl border border-white/10 bg-black/30 p-8 shadow-2xl shadow-indigo-500/15 backdrop-blur md:flex-row md:items-center md:justify-between">
        <div className="space-y-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-indigo-200/80">
            Workspace Overview
          </p>
          <h1 className="text-3xl font-semibold text-white">Automation pulse</h1>
          <p className="max-w-2xl text-sm text-zinc-300">
            Keep an eye on requests flowing through AstraForge, recent automation runs, and your API access without bouncing between sections.
          </p>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Button asChild variant="brand" className="rounded-xl">
              <Link to="/app/requests">
                <PlayCircle className="mr-2 h-4 w-4" />
                Start a request
              </Link>
            </Button>
          </div>
        </div>
        <div className="w-full max-w-xs rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-zinc-200 shadow-inner shadow-indigo-500/20">
          <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-indigo-100/80">
            Snapshot
          </p>
          {anyLoading ? (
            <div className="mt-3 space-y-2">
              <Skeleton className="h-5 w-24" />
              <Skeleton className="h-5 w-28" />
              <Skeleton className="h-5 w-20" />
            </div>
          ) : (
            <ul className="mt-3 space-y-2">
              <li className="flex items-center justify-between">
                <span className="text-xs text-zinc-300">Active requests</span>
                <span className="text-sm font-semibold text-white">
                  {requestStats.active}
                </span>
              </li>
              <li className="flex items-center justify-between">
                <span className="text-xs text-zinc-300">Runs recorded</span>
                <span className="text-sm font-semibold text-white">
                  {runStats.total}
                </span>
              </li>
            </ul>
          )}
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <MetricCard
          label="Active requests"
          value={requestStats.active}
          helper={
            requestsLoading
              ? undefined
              : `${requestStats.completed} completed / ${requestStats.total} total`
          }
          icon={Activity}
          loading={requestsLoading}
        />
        <MetricCard
          label="Automation runs"
          value={runStats.total}
          helper={
            runsLoading
              ? undefined
              : runStats.total === 0
                ? "No runs yet"
                : `${runStats.successful} finished cleanly`
          }
          icon={BarChart2}
          loading={runsLoading}
        />
        <MetricCard
          label="Merge requests"
          value={mergeStats.total}
          helper={
            mergeRequestsLoading
              ? undefined
              : `${mergeStats.open} open or draft`
          }
          icon={Layers}
          loading={mergeRequestsLoading}
        />
        <MetricCard
          label="Linked repositories"
          value={repositoryLinks?.length ?? 0}
          helper={
            repoLinksLoading
              ? undefined
              : repoCount > 0
                ? "Ready for delivery"
                : "Add a repository to deliver work"
          }
          icon={BadgeCheck}
          loading={repoLinksLoading}
        />
        <MetricCard
          label="Latest request"
          value={requestStats.latestTitle ?? "No requests"}
          helper={
            requestStats.latestTitle
              ? "Most recent submission"
              : "Submit a request to populate activity"
          }
          icon={PlayCircle}
          loading={requestsLoading}
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="home-card home-ring-soft border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div className="space-y-1">
              <CardTitle className="text-lg font-semibold text-white">Sandbox activity</CardTitle>
              <p className="text-sm text-zinc-300">
                Track how many sandboxes you have provisioned this week and watch for failures.
              </p>
            </div>
            <div className="flex flex-col items-end gap-2 text-xs text-zinc-200">
              <Badge className="rounded-full bg-emerald-500/15 text-emerald-100 ring-1 ring-emerald-300/40">
                Ready {sandboxStats.ready}
              </Badge>
              <Badge className="rounded-full bg-white/10 text-white ring-1 ring-white/20">
                Total {sandboxStats.total}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {sandboxSessionsLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : sandboxStats.total === 0 ? (
              <div className="rounded-2xl border border-dashed border-white/15 bg-white/5 p-5 text-sm text-zinc-300">
                No sandboxes yet. Start a deep agent conversation or create a sandbox to see activity.
              </div>
            ) : (
              <ChartContainer
                config={sandboxChartConfig}
                className="w-full rounded-2xl border border-white/10 bg-gradient-to-b from-indigo-950/60 to-black/60 p-4"
              >
                <AreaChart data={sandboxChartData}>
                  <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                  <XAxis
                    dataKey="label"
                    tickLine={false}
                    axisLine={false}
                    tickMargin={8}
                    tickFormatter={(value) => value.replace(/\s+/g, " ")}
                  />
                  <YAxis
                    allowDecimals={false}
                    tickLine={false}
                    axisLine={false}
                    tickMargin={8}
                    width={30}
                  />
                  <ChartTooltip
                    cursor={{ stroke: "rgba(255,255,255,0.2)" }}
                    content={<ChartTooltipContent hideLabel />}
                  />
                  <Area
                    dataKey="count"
                    type="monotone"
                    fill="var(--color-sandboxes)"
                    stroke="var(--color-sandboxes)"
                    strokeWidth={2}
                    fillOpacity={0.2}
                    dot={{ r: 3, strokeWidth: 0 }}
                    activeDot={{ r: 5, strokeWidth: 0 }}
                  />
                </AreaChart>
              </ChartContainer>
            )}
            <div className="flex flex-wrap gap-2 text-xs text-zinc-300">
              <Badge className="rounded-full bg-emerald-500/15 text-emerald-100 ring-1 ring-emerald-300/40">
                Ready {sandboxStats.ready}
              </Badge>
              <Badge className="rounded-full bg-amber-500/15 text-amber-100 ring-1 ring-amber-300/40">
                Starting {sandboxStats.starting}
              </Badge>
              <Badge className="rounded-full bg-rose-500/15 text-rose-100 ring-1 ring-rose-300/40">
                Failed {sandboxStats.failed}
              </Badge>
              <Badge className="rounded-full bg-white/10 text-white ring-1 ring-white/20">
                Total {sandboxStats.total}
              </Badge>
            </div>
            <div className="flex flex-wrap gap-2 text-xs text-zinc-300">
              {Object.entries(sandboxStats.modes).map(([mode, count]) => (
                <span
                  key={mode}
                  className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-3 py-1"
                >
                  <Server className="h-3.5 w-3.5 text-indigo-200" />
                  <span className="uppercase tracking-[0.15em] text-indigo-100/80">{mode}</span>
                  <span className="font-semibold text-white">{count}</span>
                </span>
              ))}
              {Object.keys(sandboxStats.modes).length === 0 && !sandboxSessionsLoading && (
                <span className="text-sm text-zinc-400">No sandbox modes recorded yet.</span>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="home-card home-ring-soft border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div className="space-y-1">
              <CardTitle className="text-lg font-semibold text-white">Recent requests</CardTitle>
              <p className="text-sm text-zinc-300">
                Jump back into active work or monitor the latest automation decisions.
              </p>
            </div>
            <Badge variant="secondary" className="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs text-white">
              {requestStats.total} total
            </Badge>
          </CardHeader>
          <CardContent>
            {requestsLoading ? (
              <div className="space-y-3">
                {[...Array(3)].map((_, idx) => (
                  <Skeleton key={idx} className="h-16 w-full" />
                ))}
              </div>
            ) : highlightedRequests.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-white/15 bg-white/5 p-5 text-sm text-zinc-300">
                No requests yet. Create one to see it here.
              </div>
            ) : (
              <ul className="space-y-3">
                {highlightedRequests.map((request) => {
                  const state = request.state.replace(/_/g, " ");
                  return (
                    <li key={request.id}>
                      <Link
                        to={`/app/requests/${request.id}/run`}
                        className="group block rounded-2xl border border-white/10 bg-white/5 px-4 py-3 transition hover:-translate-y-0.5 hover:border-indigo-300/50 hover:bg-white/10"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 space-y-1">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-indigo-100/70">
                              Request
                            </p>
                            <h3 className="truncate text-base font-semibold text-white group-hover:text-indigo-100">
                              {request.payload.title}
                            </h3>
                            <p className="line-clamp-2 text-sm text-zinc-300">
                              {request.payload.description}
                            </p>
                          </div>
                          <Badge className="shrink-0 rounded-full bg-indigo-500/15 px-3 py-1 text-[11px] capitalize text-indigo-100 ring-1 ring-indigo-400/30">
                            {state}
                          </Badge>
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <Button asChild variant="ghost" className="rounded-xl border border-white/10 bg-white/5 text-white hover:border-indigo-300/40 hover:bg-white/10">
                <Link to="/app/requests">
                  View request inbox
                </Link>
              </Button>
              <Button asChild variant="ghost" className="rounded-xl border border-white/10 bg-white/5 text-white hover:border-indigo-300/40 hover:bg-white/10">
                <Link to="/app/deep-sandbox">
                  Open deep sandbox
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>

      </div>
    </div>
  );
}
