import { useState } from "react";
import { NavLink } from "react-router-dom";
import {
  ActivitySquare,
  BarChart3,
  Brain,
  Check,
  History,
  Inbox,
  Infinity,
  KeyRound,
  LayoutDashboard,
  Link2,
  LogOut,
  Network,
  Sparkles,
  Zap
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { formatPlanLabel } from "@/lib/plan-label";
import { WorkspaceSwitcher } from "@/features/workspaces/components/workspace-switcher";
import { useWorkspace } from "@/features/workspaces/workspace-context";
import { useWorkspaceUsage } from "@/features/workspaces/hooks/use-workspace-usage";

const planMetadata: Record<
  string,
  {
    label: string;
    price: string;
    cadence: string;
    tagline: string;
    cta: string;
    highlight?: boolean;
    badge?: string;
    accentClass?: string;
    credit?: string;
  }
> = {
  trial: {
    label: "Trial",
    price: "$0",
    cadence: "+ usage",
    tagline: "Start exploring AstraForge sandboxes and requests.",
    cta: "Get started for free",
    credit: "$25 builder credit",
    highlight: true
  },
  pro: {
    label: "Pro",
    price: "$250",
    cadence: "+ usage",
    tagline: "For teams running daily automations with approvals.",
    cta: "Get started for free",
    badge: "Recommended",
    accentClass: "from-emerald-500/60 via-emerald-600/70 to-emerald-800/80",
    credit: "First month free"
  },
  enterprise: {
    label: "Enterprise",
    price: "Contact us",
    cadence: "",
    tagline: "Full governance, SSO, and premium support.",
    cta: "Talk to sales"
  },
  self_hosted: {
    label: "Self hosted",
    price: "Custom",
    cadence: "",
    tagline: "Run AstraForge inside your VPC with full control.",
    cta: "Contact us"
  }
};

const defaultPlanCatalog = {
  trial: {
    requests_per_month: 50,
    sandbox_sessions_per_month: 20,
    sandbox_concurrent: 1
  },
  pro: {
    requests_per_month: 500,
    sandbox_sessions_per_month: 200,
    sandbox_concurrent: 3
  },
  enterprise: {
    requests_per_month: 2000,
    sandbox_sessions_per_month: 1000,
    sandbox_concurrent: 10
  },
  self_hosted: {
    requests_per_month: null,
    sandbox_sessions_per_month: null,
    sandbox_concurrent: null
  }
};

const numberFormatter = new Intl.NumberFormat("en-US");

function formatDuration(seconds?: number | null) {
  if (!seconds || seconds <= 0) {
    return "0 min";
  }
  if (seconds < 60) {
    return "<1 min";
  }
  const totalMinutes = seconds / 60;
  if (totalMinutes < 60) {
    return `${Math.max(1, Math.round(totalMinutes))} min`;
  }
  const totalHours = totalMinutes / 60;
  if (totalHours < 24) {
    const rounded = totalHours >= 10 ? Math.round(totalHours) : totalHours.toFixed(1);
    return `${rounded} hr`;
  }
  const totalDays = totalHours / 24;
  const rounded = totalDays >= 10 ? Math.round(totalDays) : totalDays.toFixed(1);
  return `${rounded} d`;
}

function formatBytes(bytes?: number | null) {
  if (!bytes || bytes <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const rounded =
    value >= 10 || unitIndex === 0 ? Math.round(value) : Number(value.toFixed(1));
  return `${rounded} ${units[unitIndex]}`;
}

function formatPeriodLabel(period?: string | null) {
  if (!period) return null;
  const date = new Date(period);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

function formatResetLabel(period?: string | null) {
  if (!period) return null;
  const start = new Date(period);
  if (Number.isNaN(start.getTime())) return null;
  const next = new Date(start);
  next.setMonth(next.getMonth() + 1);
  next.setDate(1);
  next.setHours(0, 0, 0, 0);
  const now = new Date();
  const diff = Math.max(next.getTime() - now.getTime(), 0);
  const days = Math.ceil(diff / (1000 * 60 * 60 * 24));
  if (days <= 0) return "Renews soon";
  if (days === 1) return "Resets in 1 day";
  return `Resets in ${days} days`;
}

const navItems = [
  { to: "/app", label: "Overview", icon: LayoutDashboard, exact: true },
  { to: "/app/activity-logs", label: "Activity logs", icon: History },
  { to: "/app/usage", label: "Usage", icon: BarChart3 },
  { to: "/app/requests", label: "Requests", icon: Inbox },
  { to: "/app/repositories", label: "Repositories", icon: Link2 },
  { to: "/app/api-keys", label: "API Keys", icon: KeyRound },
  { to: "/app/deep-sandbox", label: "Deep Agent Sandbox", icon: Brain }
];

export function Sidebar() {
  const { logout, authSettings, isAuthenticated } = useAuth();
  const { activeWorkspace } = useWorkspace();
  const billingEnabled = authSettings?.billing_enabled ?? true;
  const {
    data: workspaceUsage,
    isLoading: usageLoading,
    isError: usageError
  } = useWorkspaceUsage(activeWorkspace?.uid);
  const planKey = (workspaceUsage?.plan || activeWorkspace?.plan || "trial").toLowerCase();
  const currentPlanMeta =
    planMetadata[planKey] ??
    {
      label: formatPlanLabel(planKey) ?? planKey,
      price: "Custom",
      cadence: "",
      tagline: "Tailored plan.",
      cta: "Contact us"
    };
  const planLabel = currentPlanMeta.label || formatPlanLabel(planKey) || "Workspace plan";
  const usageLabel = billingEnabled ? planLabel : "Usage";
  const usageTagline = billingEnabled
    ? currentPlanMeta.tagline
    : "Usage tracking for this workspace.";
  const rawCatalog =
    workspaceUsage?.catalog && Object.keys(workspaceUsage.catalog).length > 0
      ? workspaceUsage.catalog
      : defaultPlanCatalog;
  const planPriority = ["trial", "pro", "team", "enterprise", "self_hosted"];
  const planCatalog = Object.entries(rawCatalog).sort((a, b) => {
    const [keyA] = a;
    const [keyB] = b;
    const rankA = planPriority.indexOf(keyA);
    const rankB = planPriority.indexOf(keyB);
    return (rankA === -1 ? 99 : rankA) - (rankB === -1 ? 99 : rankB);
  });
  const sandboxRuntimeSeconds = workspaceUsage?.usage?.sandbox_seconds ?? 0;
  const artifactsBytes = workspaceUsage?.usage?.artifacts_bytes ?? 0;
  const quotaItems = [
    {
      key: "requests",
      label: "Requests",
      helper: "Per month",
      used: workspaceUsage?.usage?.requests_per_month ?? 0,
      limit: workspaceUsage?.limits?.requests_per_month ?? null,
      icon: ActivitySquare
    },
    {
      key: "sandbox_sessions",
      label: "Sandbox sessions",
      helper: "Per month",
      used: workspaceUsage?.usage?.sandbox_sessions_per_month ?? 0,
      limit: workspaceUsage?.limits?.sandbox_sessions_per_month ?? null,
      icon: Zap
    },
    {
      key: "active_sandboxes",
      label: "Active sandboxes",
      helper: "Concurrent",
      used: workspaceUsage?.usage?.active_sandboxes ?? 0,
      limit: workspaceUsage?.limits?.sandbox_concurrent ?? null,
      icon: Network
    }
  ];
  const [planDialogOpen, setPlanDialogOpen] = useState(false);
  const billingCycleLabel = formatPeriodLabel(workspaceUsage?.period_start);
  const billingMeters = [
    {
      meter: "Automation runtime",
      helper: "Sandbox CPU time this billing cycle",
      usage: formatDuration(sandboxRuntimeSeconds),
      rate: "$0.00009 per CPU / sec"
    },
    {
      meter: "Storage footprint",
      helper: "Snapshots & artifacts retained",
      usage: formatBytes(artifactsBytes),
      rate: "$0.000002 per GB / sec"
    },
    {
      meter: "Bandwidth",
      helper: "Network metering launches next",
      usage: "Coming soon",
      rate: "$0.0000007 per GB"
    }
  ];
  const usageUnavailable = usageError || !workspaceUsage;

  return (
    <aside className="relative hidden h-full w-64 flex-col overflow-y-auto overflow-x-hidden border-r border-sidebar-border/70 bg-sidebar-background/90 pb-4 text-sidebar-foreground shadow-xl shadow-primary/10 lg:flex">
      <div className="relative flex items-center gap-3 px-4 pb-4 pt-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-sidebar-primary/15 text-sidebar-primary ring-1 ring-sidebar-border/80">
          <Sparkles className="h-5 w-5" />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-semibold">AstraForge</p>
          <p className="text-[11px] uppercase tracking-[0.35em] text-sidebar-foreground/60">
            Platform
          </p>
        </div>
      </div>

      <div className="relative px-3 pb-4">
        <WorkspaceSwitcher />
      </div>

      <nav className="relative mt-2 flex flex-1 flex-col gap-1 px-3">
        <p className="px-2 text-[11px] font-semibold uppercase tracking-[0.3em] text-sidebar-foreground/60">
          Navigate
        </p>
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.exact}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition",
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-inner shadow-sidebar-border/40"
                    : "text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
                )
              }
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          );
        })}
      </nav>

      <div className="relative mt-4 px-3">
        <div className="rounded-2xl border border-sidebar-border/70 bg-sidebar-background/70 p-3 text-xs text-sidebar-foreground shadow-inner shadow-black/20">
          <div className="space-y-0.5">
            <p className="text-[10px] font-semibold uppercase tracking-[0.35em] text-sidebar-foreground/60">
              {usageLabel}
            </p>
            <p className="text-[11px] text-sidebar-foreground/70">{usageTagline}</p>
          </div>
          <div className="mt-3 space-y-2">
            {usageLoading || usageError || !workspaceUsage ? (
              <div className="space-y-2">
                <Skeleton className="h-2 w-full rounded-full" />
                <Skeleton className="h-2 w-5/6 rounded-full" />
              </div>
            ) : (
              quotaItems.map((item) => {
                const limit = item.limit;
                const effectiveLimit = billingEnabled ? limit : null;
                const used = item.used;
                const Icon = item.icon;
                const hasLimit =
                  typeof effectiveLimit === "number" && effectiveLimit > 0;
                const pct = hasLimit
                  ? Math.min((used / (effectiveLimit ?? 0)) * 100, 100)
                  : 0;
                const remaining = hasLimit
                  ? Math.max((effectiveLimit ?? 0) - used, 0)
                  : null;
                const limitLabel = hasLimit ? (
                  `${numberFormatter.format(remaining ?? 0)} remaining / ${numberFormatter.format(effectiveLimit ?? 0)}`
                ) : (
                  <span className="inline-flex items-center gap-1" title="Unlimited">
                    <Infinity className="h-3 w-3" aria-hidden="true" />
                    <span className="sr-only">Unlimited</span>
                    <span>· {numberFormatter.format(used)} used</span>
                  </span>
                );
                return (
                  <div key={item.key} className="space-y-1">
                    <div className="flex items-center justify-between gap-2 text-[11px] font-semibold">
                      <div className="flex items-center gap-2 text-sidebar-foreground/80">
                        <Icon className="h-3.5 w-3.5" />
                        <span>{item.label}</span>
                      </div>
                      <div className="text-[10px] text-sidebar-foreground/70">{limitLabel}</div>
                    </div>
                    {hasLimit ? (
                      <Progress value={pct} className="h-1 rounded-full bg-sidebar-border/60" />
                    ) : (
                      <div className="h-1 rounded-full border border-dashed border-sidebar-border/70" />
                    )}
                  </div>
                );
              })
            )}
          </div>
          {billingEnabled ? (
            <div className="mt-3 flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.3em] text-sidebar-foreground/60">
              <button
                type="button"
                onClick={() => setPlanDialogOpen(true)}
                className="inline-flex items-center gap-1 text-sidebar-foreground hover:text-sidebar-foreground/80"
              >
                Manage plan
                <span aria-hidden="true">›</span>
              </button>
              <span>{formatResetLabel(workspaceUsage?.period_start) ?? "Resets soon"}</span>
            </div>
          ) : null}
        </div>
      </div>

      <div className="relative mt-6 px-3">
        <div className="flex items-center justify-between rounded-xl border border-sidebar-border/80 bg-sidebar-background/70 px-3 py-2 text-sm text-sidebar-foreground/80">
          <div>
            <p className="text-[11px] uppercase tracking-[0.3em] text-sidebar-foreground/60">
              Session
            </p>
            <p className="text-sm font-medium text-sidebar-foreground">
              {isAuthenticated ? "Signed out" : "Signed in"}
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-lg text-sidebar-foreground hover:bg-sidebar-accent/60"
            onClick={async () => {
              await logout();
              window.location.href = "/login";
            }}
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </div>
      {billingEnabled ? (
        <Dialog open={planDialogOpen} onOpenChange={setPlanDialogOpen}>
          <DialogContent className="max-w-[90rem]">
            <DialogHeader>
              <DialogTitle>Manage your plan</DialogTitle>
              <p className="text-sm text-muted-foreground">
                Compare what&apos;s included at each tier, unlock more automation minutes, and plan
                ahead for upcoming workloads.
              </p>
            </DialogHeader>
            {usageLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-10 w-full rounded-xl" />
                <Skeleton className="h-10 w-full rounded-xl" />
              </div>
            ) : (
                <div className="space-y-6">
                  <div className="space-y-1">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-muted-foreground">
                      Plans
                    </p>
                    <p className="text-base text-muted-foreground">
                    All plans are billed monthly. Contact us for annual discounts or enterprise
                    agreements.
                  </p>
                </div>
                <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
                  {planCatalog.map(([planKey, limits]) => {
                    const metadata = planMetadata[planKey] ?? {
                      label: formatPlanLabel(planKey) ?? planKey,
                      price: "Custom",
                      cadence: "",
                      tagline: "Tailored plan.",
                      cta: "Contact us"
                    };
                    const isCurrent = (workspaceUsage?.plan || activeWorkspace?.plan) === planKey;
                    const features = [
                      limits.requests_per_month != null
                        ? `${numberFormatter.format(limits.requests_per_month)} requests / month`
                        : "Unlimited requests per month",
                      limits.sandbox_sessions_per_month != null
                        ? `${numberFormatter.format(
                            limits.sandbox_sessions_per_month
                          )} sandbox sessions / month`
                        : "Unlimited sandbox sessions",
                      limits.sandbox_concurrent != null
                        ? `${numberFormatter.format(limits.sandbox_concurrent)} concurrent sandboxes`
                        : "Unlimited concurrent sandboxes"
                    ];
                    return (
                      <div
                        key={planKey}
                        className={cn(
                          "flex h-full flex-col rounded-[2rem] border px-6 py-7 shadow-xl transition",
                          metadata.highlight
                            ? "border-transparent bg-gradient-to-br from-primary/30 via-primary/10 to-background"
                            : "border-border/40 bg-card/80",
                          isCurrent && "ring-2 ring-primary/40",
                          metadata.accentClass && "bg-gradient-to-br " + metadata.accentClass
                        )}
                      >
                        <div className="space-y-2">
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-sm font-semibold uppercase tracking-[0.3em] text-muted-foreground">
                              {metadata.label}
                            </p>
                            {metadata.badge ? (
                              <span className="rounded-full bg-primary/20 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.3em] text-primary-foreground/80">
                                {metadata.badge}
                              </span>
                            ) : null}
                          </div>
                          <div className="flex items-end gap-2">
                            <p className="text-4xl font-semibold text-foreground">{metadata.price}</p>
                            {metadata.cadence ? (
                              <span className="text-xs uppercase tracking-[0.3em] text-muted-foreground">
                                {metadata.cadence}
                              </span>
                            ) : null}
                          </div>
                          {metadata.credit ? (
                            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-primary">
                              {metadata.credit}
                            </p>
                          ) : null}
                          <p className="text-sm text-muted-foreground">{metadata.tagline}</p>
                        </div>
                        <div className="mt-4">
                          <Button
                            variant={isCurrent ? "secondary" : "default"}
                            disabled
                            className="w-full rounded-2xl"
                          >
                            {isCurrent ? "Current plan" : metadata.cta}
                          </Button>
                        </div>
                        <div className="mt-4 flex-1 space-y-2 text-sm text-muted-foreground">
                          {features.map((feature, index) => (
                            <div key={String(index)} className="flex items-start gap-2">
                              <Check className="mt-0.5 h-4 w-4 text-primary" />
                              <span>{feature}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="grid gap-4 rounded-2xl border border-border/60 bg-muted/20 p-4 text-xs text-muted-foreground md:grid-cols-[1fr,minmax(0,1.4fr)]">
                  <div className="space-y-2 text-sm">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.35em]">
                      Usage billing
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Usage fees are calculated separately from your plan based on actual consumption.
                    </p>
                    {billingCycleLabel ? (
                      <p className="text-xs text-muted-foreground/80">
                        Current cycle since {billingCycleLabel}.
                      </p>
                    ) : null}
                  </div>
                  <div className="overflow-hidden rounded-2xl border border-border/60 bg-card/60">
                    {usageUnavailable ? (
                      <div className="px-4 py-6 text-sm text-muted-foreground">
                        Usage metrics are unavailable right now. Visit the Usage page for details.
                      </div>
                    ) : (
                      <>
                        <div className="grid grid-cols-3 border-b border-border/40 text-[10px] uppercase tracking-[0.35em] text-muted-foreground">
                          <span className="px-3 py-2 text-left">Meter</span>
                          <span className="px-3 py-2 text-center">This period</span>
                          <span className="px-3 py-2 text-right">Rate</span>
                        </div>
                        {billingMeters.map((item) => (
                          <div
                            key={item.meter}
                            className="grid grid-cols-3 border-b border-border/30 text-sm last:border-b-0"
                          >
                            <div className="px-3 py-3">
                              <p className="font-medium text-foreground">{item.meter}</p>
                              <p className="text-xs text-muted-foreground">{item.helper}</p>
                            </div>
                            <div className="px-3 py-3 text-center text-sm font-semibold text-foreground">
                              {item.usage}
                            </div>
                            <div className="px-3 py-3 text-right text-sm text-muted-foreground">
                              {item.rate}
                            </div>
                          </div>
                        ))}
                      </>
                    )}
                  </div>
                  <div className="col-span-full rounded-2xl border border-border/60 bg-muted/40 px-4 py-3 text-xs text-muted-foreground">
                    Looking for private networking, VPC deployments, or SSO? Email{" "}
                    <a href="mailto:contact@astraforge.dev" className="text-primary underline">
                      contact@astraforge.dev
                    </a>{" "}
                    and we&apos;ll craft a plan for your team.
                  </div>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>
      ) : null}
    </aside>
  );
}
