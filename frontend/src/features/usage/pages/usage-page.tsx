import { useMemo } from "react";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { useQueryClient } from "@tanstack/react-query";
import { Activity, BarChart2, Cpu, Rocket, Server } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent
} from "@/components/ui/chart";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useApiKeys } from "@/features/api-keys/hooks/use-api-keys";
import { useRequests } from "@/features/requests/hooks/use-requests";
import { useRuns } from "@/features/runs/hooks/use-runs";
import { useSandboxSessions } from "@/features/sandbox/hooks/use-sandbox-sessions";
import { useWorkspace } from "@/features/workspaces/workspace-context";
import { useWorkspaceUsage } from "@/features/workspaces/hooks/use-workspace-usage";
import { formatPlanLabel } from "@/lib/plan-label";

function formatDuration(seconds?: number | null) {
  if (!seconds || seconds <= 0) return "0 min";
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
  if (!bytes || bytes <= 0) return "0 B";
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

type MetricCardProps = {
  label: string;
  value: string | number;
  helper?: string;
  tone?: "indigo" | "emerald" | "amber" | "sky";
  loading?: boolean;
};

function MetricCard({ label, value, helper, tone = "indigo", loading }: MetricCardProps) {
  const toneClass =
    tone === "emerald"
      ? "bg-emerald-500/10 text-emerald-100 ring-emerald-500/30"
      : tone === "amber"
        ? "bg-amber-500/10 text-amber-100 ring-amber-500/30"
        : tone === "sky"
          ? "bg-sky-500/10 text-sky-100 ring-sky-500/30"
          : "bg-indigo-500/10 text-indigo-100 ring-indigo-500/30";

  return (
    <Card className="home-card home-ring-soft rounded-2xl border border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
      <CardContent className="p-5">
        <div className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] ring-1 ${toneClass}`}>
          {label}
        </div>
        {loading ? (
          <div className="mt-4 space-y-2">
            <Skeleton className="h-7 w-16" />
            {helper ? <Skeleton className="h-4 w-32" /> : null}
          </div>
        ) : (
          <>
            <p className="mt-3 text-3xl font-semibold text-white">{value}</p>
            {helper ? <p className="text-sm text-zinc-300">{helper}</p> : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function normalizeDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date;
}

export default function UsagePage() {
  const queryClient = useQueryClient();
  const { activeWorkspace } = useWorkspace();
  const workspaceUid = activeWorkspace?.uid;
  const workspacePlanLabel = formatPlanLabel(activeWorkspace?.plan);
  const { data: requests, isLoading: requestsLoading } = useRequests(workspaceUid);
  const { data: runs, isLoading: runsLoading } = useRuns();
  const { data: sandboxSessions, isLoading: sandboxSessionsLoading } = useSandboxSessions();
  const { data: apiKeys, isLoading: apiKeysLoading } = useApiKeys();
  const {
    data: workspaceUsage,
    isLoading: workspaceUsageLoading,
    isError: workspaceUsageError
  } = useWorkspaceUsage(workspaceUid);

  const scopedRequestIds = useMemo(
    () => new Set((requests ?? []).map((request) => request.id)),
    [requests]
  );
  const scopedRuns = useMemo(
    () => (runs ?? []).filter((run) => scopedRequestIds.has(run.request_id)),
    [runs, scopedRequestIds]
  );

  const requestStats = useMemo(() => {
    const list = requests ?? [];
    const latest = list
      .slice()
      .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))
      .at(0);
    return {
      total: list.length,
      latestTitle: latest?.payload.title ?? null
    };
  }, [requests]);

  const runStats = useMemo(() => {
    const list = scopedRuns ?? [];
    const success = list.filter((run) => {
      const state = (run.status || "").toLowerCase();
      return state.includes("success") || state.includes("done") || state.includes("complete");
    }).length;
    const averageDiff =
      list.length > 0
        ? Math.round(list.reduce((total, run) => total + (run.diff_size || 0), 0) / list.length)
        : 0;
    return {
      total: list.length,
      success,
      successRate: list.length > 0 ? Math.round((success / list.length) * 100) : 0,
      averageDiff
    };
  }, [scopedRuns]);

  const sandboxStats = useMemo(() => {
    const list = sandboxSessions ?? [];
    let ready = 0;
    let starting = 0;
    let failed = 0;
    list.forEach((session) => {
      const status = (session.status || "").toLowerCase();
      if (status.includes("ready")) ready += 1;
      else if (status.includes("start")) starting += 1;
      else if (status.includes("fail")) failed += 1;
    });
    return { total: list.length, ready, starting, failed };
  }, [sandboxSessions]);

  const apiKeyStats = useMemo(() => {
    const list = apiKeys ?? [];
    const active = list.filter((key) => key.is_active).length;
    const recentlyUsed = list
      .slice()
      .sort((a, b) => (b.last_used_at || "").localeCompare(a.last_used_at || ""))
      .at(0);
    return { total: list.length, active, recentlyUsedAt: recentlyUsed?.last_used_at ?? null };
  }, [apiKeys]);

  const usageChartData = useMemo(() => {
    const buckets: Record<string, { requests: number; runs: number; label: string }> = {};
    const today = new Date();
    const dayKeys = Array.from({ length: 10 }).map((_, idx) => {
      const day = new Date(today);
      day.setDate(today.getDate() - (9 - idx));
      const key = day.toISOString().slice(0, 10);
      const label = day.toLocaleDateString(undefined, { month: "short", day: "numeric" });
      buckets[key] = { requests: 0, runs: 0, label };
      return key;
    });

    (requests ?? []).forEach((request) => {
      const date = normalizeDate(request.created_at);
      if (!date) return;
      const key = date.toISOString().slice(0, 10);
      if (!buckets[key]) return;
      buckets[key].requests += 1;
    });

    (scopedRuns ?? []).forEach((run) => {
      const date = normalizeDate(run.started_at || run.finished_at);
      if (!date) return;
      const key = date.toISOString().slice(0, 10);
      if (!buckets[key]) return;
      buckets[key].runs += 1;
    });

    return dayKeys.map((key) => ({
      key,
      label: buckets[key].label,
      requests: buckets[key].requests,
      runs: buckets[key].runs
    }));
  }, [requests, scopedRuns]);

  const chartConfig = {
    requests: {
      label: "Requests",
      color: "hsl(222, 89%, 60%)"
    },
    runs: {
      label: "Runs",
      color: "hsl(142, 72%, 45%)"
    }
  };

  const sandboxChartData = useMemo(() => {
    const buckets: Record<string, { total: number; label: string }> = {};
    const today = new Date();
    const dayKeys = Array.from({ length: 10 }).map((_, idx) => {
      const day = new Date(today);
      day.setDate(today.getDate() - (9 - idx));
      const key = day.toISOString().slice(0, 10);
      const label = day.toLocaleDateString(undefined, { month: "short", day: "numeric" });
      buckets[key] = { total: 0, label };
      return key;
    });

    (sandboxSessions ?? []).forEach((session) => {
      const date = normalizeDate(session.created_at || session.updated_at);
      if (!date) return;
      const key = date.toISOString().slice(0, 10);
      if (!buckets[key]) return;
      buckets[key].total += 1;
    });

    return dayKeys.map((key) => ({
      key,
      label: buckets[key].label,
      sandboxes: buckets[key].total
    }));
  }, [sandboxSessions]);

  const sandboxChartConfig = {
    sandboxes: {
      label: "Sandboxes",
      color: "hsl(199, 89%, 62%)"
    }
  };

  const consumptionMetrics =
    workspaceUsage
      ? [
          {
            key: "requests",
            label: "Requests",
            helper: "per month",
            used: workspaceUsage.usage.requests_per_month ?? 0,
            limit: workspaceUsage.limits.requests_per_month ?? null
          },
          {
            key: "sandbox_sessions",
            label: "Sandbox sessions",
            helper: "per month",
            used: workspaceUsage.usage.sandbox_sessions_per_month ?? 0,
            limit: workspaceUsage.limits.sandbox_sessions_per_month ?? null
          },
          {
            key: "active_sandboxes",
            label: "Active sandboxes",
            helper: "concurrent",
            used: workspaceUsage.usage.active_sandboxes ?? 0,
            limit: workspaceUsage.limits.sandbox_concurrent ?? null
          }
        ]
      : [];

  const meterSummaries = workspaceUsage
    ? [
        {
          key: "runtime",
          label: "Automation runtime",
          value: formatDuration(workspaceUsage.usage.sandbox_seconds),
          helper: "Sandbox CPU time this cycle"
        },
        {
          key: "storage",
          label: "Storage footprint",
          value: formatBytes(workspaceUsage.usage.artifacts_bytes),
          helper: "Snapshots & artifacts retained"
        }
      ]
    : [];

  const loading =
    requestsLoading ||
    runsLoading ||
    sandboxSessionsLoading ||
    apiKeysLoading ||
    workspaceUsageLoading;

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["requests"] });
    queryClient.invalidateQueries({ queryKey: ["runs"] });
    queryClient.invalidateQueries({ queryKey: ["sandbox-sessions"] });
    queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    if (workspaceUid) {
      queryClient.invalidateQueries({ queryKey: ["workspace-usage", workspaceUid] });
    }
  };

  return (
    <div className="relative z-10 mx-auto w-full max-w-[clamp(64rem,76vw,104rem)] space-y-8 px-4 py-8 text-zinc-100 sm:px-6 lg:px-10">
      <section className="home-card home-ring-soft space-y-4 rounded-3xl border border-white/10 bg-black/30 p-8 shadow-2xl shadow-indigo-500/15 backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-indigo-200/80">
              Utilization
            </p>
            <h1 className="text-3xl font-semibold text-white">Usage</h1>
            <p className="max-w-2xl text-sm text-zinc-300">
              Monitor how teams are leaning on AstraForge across requests, automation runs, sandboxes, and API access.
            </p>
            {activeWorkspace ? (
              <p className="text-xs font-medium uppercase tracking-[0.3em] text-zinc-400">
                Workspace · {activeWorkspace.name}
              </p>
            ) : null}
          </div>
          <div className="flex items-center gap-3">
            {workspacePlanLabel ? (
              <Badge className="rounded-2xl border border-white/15 bg-white/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.3em] text-white">
                Plan · {workspacePlanLabel}
              </Badge>
            ) : null}
            <Button
              variant="outline"
              size="sm"
              className="rounded-xl border-white/20 text-white hover:border-indigo-300/60 hover:text-indigo-100"
              onClick={handleRefresh}
            >
              Refresh data
            </Button>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Badge className="flex items-center justify-between gap-2 rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm text-white">
            <span className="uppercase tracking-[0.15em] text-xs text-indigo-100/80">
              Requests
            </span>
            <span className="text-base font-semibold">{requestStats.total}</span>
          </Badge>
          <Badge className="flex items-center justify-between gap-2 rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm text-white">
            <span className="uppercase tracking-[0.15em] text-xs text-emerald-100/80">
              Runs
            </span>
            <span className="text-base font-semibold">{runStats.total}</span>
          </Badge>
          <Badge className="flex items-center justify-between gap-2 rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm text-white">
            <span className="uppercase tracking-[0.15em] text-xs text-sky-100/80">
              Sandboxes
            </span>
            <span className="text-base font-semibold">{sandboxStats.total}</span>
          </Badge>
          <Badge className="flex items-center justify-between gap-2 rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm text-white">
            <span className="uppercase tracking-[0.15em] text-xs text-amber-100/80">
              API Keys
            </span>
            <span className="text-base font-semibold">{apiKeyStats.total}</span>
          </Badge>
        </div>
      </section>

      <section className="home-card home-ring-soft rounded-3xl border border-white/10 bg-black/30 p-6 text-zinc-100 shadow-2xl shadow-indigo-500/15 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-indigo-100/70">
              Consumption
            </p>
            <h2 className="text-xl font-semibold text-white">Monthly limits & meters</h2>
            {workspaceUsage?.period_start ? (
              <p className="text-xs text-zinc-400">
                Cycle since{" "}
                {new Date(workspaceUsage.period_start).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric"
                })}
              </p>
            ) : null}
          </div>
        </div>
        <div className="mt-4 space-y-3">
          {workspaceUsageLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-2 w-full rounded-full" />
              <Skeleton className="h-2 w-5/6 rounded-full" />
              <Skeleton className="h-2 w-3/4 rounded-full" />
            </div>
          ) : workspaceUsageError ? (
            <p className="text-sm text-zinc-300">Unable to load workspace limits right now.</p>
          ) : !workspaceUsage ? (
            <p className="text-sm text-zinc-300">Select a workspace to review consumption.</p>
          ) : (
            <>
              <div className="space-y-3">
                {consumptionMetrics.map((metric) => {
                  const hasLimit = typeof metric.limit === "number" && metric.limit > 0;
                  const remaining = hasLimit ? Math.max((metric.limit ?? 0) - metric.used, 0) : null;
                  const pct = hasLimit && metric.limit ? Math.min((metric.used / metric.limit) * 100, 100) : 0;
                  return (
                    <div key={metric.key} className="space-y-1">
                      <div className="flex items-center justify-between text-sm font-semibold">
                        <div className="text-zinc-100">{metric.label}</div>
                        <div className="text-zinc-300 text-xs">
                          {hasLimit
                            ? `${numberFormatter.format(remaining ?? 0)} remaining / ${numberFormatter.format(metric.limit ?? 0)}`
                            : `${numberFormatter.format(metric.used)} used`}
                        </div>
                      </div>
                      {hasLimit ? (
                        <Progress value={pct} className="h-1.5 rounded-full bg-white/10" />
                      ) : (
                        <div className="h-1.5 rounded-full border border-dashed border-white/20" />
                      )}
                    </div>
                  );
                })}
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {meterSummaries.map((meter) => (
                  <div
                    key={meter.key}
                    className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-zinc-200"
                  >
                    <p className="text-xs font-semibold uppercase tracking-[0.3em] text-zinc-400">
                      {meter.label}
                    </p>
                    <p className="text-lg font-semibold text-white">{meter.value}</p>
                    <p className="text-xs text-zinc-400">{meter.helper}</p>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        <MetricCard
          label="Runs success"
          value={`${runStats.successRate}%`}
          helper={`${runStats.success} of ${runStats.total} runs completed`}
          tone="emerald"
          loading={runsLoading}
        />
        <MetricCard
          label="Average diff size"
          value={`${runStats.averageDiff} lines`}
          helper="Mean diff size across finished runs"
          tone="indigo"
          loading={runsLoading}
        />
        <MetricCard
          label="Sandboxes ready"
          value={`${sandboxStats.ready}/${sandboxStats.total}`}
          helper={`${sandboxStats.starting} starting • ${sandboxStats.failed} failed`}
          tone="sky"
          loading={sandboxSessionsLoading}
        />
        <MetricCard
          label="Active API keys"
          value={apiKeyStats.active}
          helper={
            apiKeyStats.recentlyUsedAt
              ? `Last used ${new Date(apiKeyStats.recentlyUsedAt).toLocaleString()}`
              : "No recent API key usage"
          }
          tone="amber"
          loading={apiKeysLoading}
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="home-card home-ring-soft rounded-3xl border border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
          <CardHeader className="flex flex-row items-center justify-between border-b border-white/10">
            <div>
              <CardTitle className="text-lg text-white">Volume over time</CardTitle>
              <p className="text-sm text-zinc-300">
                Requests versus automation runs over the past 10 days.
              </p>
            </div>
            <BarChart2 className="h-5 w-5 text-indigo-200" />
          </CardHeader>
          <CardContent className="p-6">
            {loading ? (
              <Skeleton className="h-64 w-full rounded-2xl" />
            ) : (
              <ChartContainer config={chartConfig}>
                <AreaChart data={usageChartData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} strokeOpacity={0.1} />
                  <XAxis
                    dataKey="label"
                    tickLine={false}
                    axisLine={false}
                    stroke="#A1A1AA"
                    tickMargin={8}
                  />
                  <YAxis
                    allowDecimals={false}
                    tickLine={false}
                    axisLine={false}
                    stroke="#A1A1AA"
                    tickMargin={12}
                  />
                  <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
                  <Area
                    type="monotone"
                    dataKey="requests"
                    stroke="var(--color-requests)"
                    fill="var(--color-requests)"
                    fillOpacity={0.18}
                    strokeWidth={2}
                    dot={{ strokeWidth: 0 }}
                  />
                  <Area
                    type="monotone"
                    dataKey="runs"
                    stroke="var(--color-runs)"
                    fill="var(--color-runs)"
                    fillOpacity={0.18}
                    strokeWidth={2}
                    dot={{ strokeWidth: 0 }}
                  />
                </AreaChart>
              </ChartContainer>
            )}
          </CardContent>
        </Card>

        <Card className="home-card home-ring-soft rounded-3xl border border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
          <CardHeader className="flex flex-row items-center justify-between border-b border-white/10">
            <div>
              <CardTitle className="text-lg text-white">Sandbox activity</CardTitle>
              <p className="text-sm text-zinc-300">New sandboxes created over the past 10 days.</p>
            </div>
            <Server className="h-5 w-5 text-sky-200" />
          </CardHeader>
          <CardContent className="p-6">
            {loading ? (
              <Skeleton className="h-64 w-full rounded-2xl" />
            ) : (
              <ChartContainer config={sandboxChartConfig}>
                <AreaChart data={sandboxChartData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} strokeOpacity={0.1} />
                  <XAxis
                    dataKey="label"
                    tickLine={false}
                    axisLine={false}
                    stroke="#A1A1AA"
                    tickMargin={8}
                  />
                  <YAxis
                    allowDecimals={false}
                    tickLine={false}
                    axisLine={false}
                    stroke="#A1A1AA"
                    tickMargin={12}
                  />
                  <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
                  <Area
                    type="monotone"
                    dataKey="sandboxes"
                    stroke="var(--color-sandboxes)"
                    fill="var(--color-sandboxes)"
                    fillOpacity={0.18}
                    strokeWidth={2}
                    dot={{ strokeWidth: 0 }}
                  />
                </AreaChart>
              </ChartContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="home-card home-ring-soft rounded-3xl border border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
        <CardHeader className="flex flex-row items-center justify-between border-b border-white/10">
          <div>
            <CardTitle className="text-lg text-white">Highlights</CardTitle>
            <p className="text-sm text-zinc-300">
              Quick wins to keep tabs on without diving into each section.
            </p>
          </div>
          <Rocket className="h-5 w-5 text-emerald-200" />
        </CardHeader>
        <CardContent className="grid gap-3 p-6 md:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <Activity className="h-4 w-4 text-indigo-200" />
              Latest request
            </div>
            <p className="mt-2 text-sm text-zinc-300">
              {requestStats.latestTitle ?? "No requests submitted yet."}
            </p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <Cpu className="h-4 w-4 text-emerald-200" />
              Automation health
            </div>
            <p className="mt-2 text-sm text-zinc-300">
              {runStats.total === 0
                ? "No runs yet."
                : `${runStats.successRate}% success rate across recent runs.`}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
