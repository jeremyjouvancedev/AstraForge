import type { FormEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  MousePointerClick,
  ShieldAlert
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/sonner";
import { cn } from "@/lib/utils";
import {
  useAcknowledgeComputerUseRun,
  useComputerUseRun,
  useComputerUseRuns,
  useComputerUseTimeline,
  useCreateComputerUseRun
} from "@/features/computer-use/hooks/use-computer-use";
import { useSandboxSessions } from "@/features/sandbox/hooks/use-sandbox-sessions";
import type {
  ComputerUseRun,
  ComputerUseTimelineItem,
  CreateComputerUseRunInput,
  SandboxSession
} from "@/lib/api-client";

type ApprovalMode = "auto" | "on_risk" | "always";
type SandboxStrategy = "new" | "existing";

const statusLabels: Record<string, string> = {
  awaiting_ack: "Awaiting approval",
  blocked_policy: "Blocked by policy",
  denied_approval: "Denied approval",
  execution_error: "Execution error",
  max_steps: "Max steps",
  timed_out: "Timed out",
  user_cancel: "User canceled"
};

const defaultComputerUseImage = "astraforge/computer-use:latest";

const approvalModeOptions: Array<{
  value: ApprovalMode;
  label: string;
  helper: string;
}> = [
  {
    value: "auto",
    label: "Auto",
    helper: "Block hard violations only."
  },
  {
    value: "on_risk",
    label: "On risk",
    helper: "Approval for medium/high risk steps."
  },
  {
    value: "always",
    label: "Always",
    helper: "Approval for every action."
  }
];

const inputClassName =
  "rounded-xl border-white/10 bg-black/30 text-zinc-100 ring-1 ring-white/5 placeholder:text-zinc-500 focus-visible:border-indigo-400/60 focus-visible:ring-indigo-400/60 focus-visible:ring-offset-0";
const selectTriggerClassName =
  "h-11 w-full rounded-xl border border-white/10 bg-black/30 px-4 text-sm text-zinc-100 ring-1 ring-white/5 focus-visible:ring-2 focus-visible:ring-indigo-400/60 focus-visible:ring-offset-0";
const selectContentClassName =
  "rounded-xl border border-white/10 bg-black/90 text-zinc-100 shadow-2xl shadow-indigo-500/20 backdrop-blur";

export function parseDomainList(raw: string): string[] {
  const entries = raw
    .split(/[\n,]+/)
    .flatMap((entry) => entry.split(/\s+/))
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => entry.toLowerCase());
  const seen = new Set<string>();
  const output: string[] = [];
  entries.forEach((entry) => {
    if (seen.has(entry)) return;
    seen.add(entry);
    output.push(entry);
  });
  return output;
}

function formatStatusLabel(status?: string | null) {
  if (!status) return "Unknown";
  return statusLabels[status] ?? status.replace(/_/g, " ");
}

function statusTone(status?: string | null) {
  const value = (status || "").toLowerCase();
  if (value.includes("awaiting")) return "bg-amber-500/15 text-amber-300";
  if (value.includes("running")) return "bg-primary/15 text-primary";
  if (value.includes("completed")) return "bg-emerald-500/15 text-emerald-400";
  if (value.includes("blocked") || value.includes("denied")) {
    return "bg-destructive/15 text-destructive";
  }
  if (value.includes("error") || value.includes("failed")) {
    return "bg-destructive/15 text-destructive";
  }
  if (value.includes("timed") || value.includes("max_steps") || value.includes("user_cancel")) {
    return "bg-orange-500/15 text-orange-300";
  }
  return "bg-muted/70 text-muted-foreground";
}

function severityTone(severity?: string | null) {
  if (!severity) return "bg-muted/70 text-muted-foreground";
  if (severity === "high") return "bg-destructive/15 text-destructive";
  if (severity === "medium") return "bg-amber-500/15 text-amber-300";
  return "bg-emerald-500/15 text-emerald-400";
}

function formatTimestamp(value?: string | null) {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return date.toLocaleString();
}

function parseOptionalInt(raw: string, label: string) {
  const trimmed = raw.trim();
  if (!trimmed) return { value: undefined, error: null };
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return { value: undefined, error: `${label} must be a positive number.` };
  }
  return { value: Math.floor(parsed), error: null };
}

function parseDecisionScript(raw: string) {
  const trimmed = raw.trim();
  if (!trimmed) return { script: undefined, error: null };
  try {
    const parsed = JSON.parse(trimmed);
    if (!Array.isArray(parsed)) {
      return { script: undefined, error: "Decision script must be a JSON array." };
    }
    const normalized = parsed.map((item) => {
      if (item && typeof item === "object") {
        return item as Record<string, unknown>;
      }
      throw new Error("Decision script entries must be JSON objects.");
    });
    return { script: normalized, error: null };
  } catch (error) {
    return {
      script: undefined,
      error: error instanceof Error ? error.message : "Invalid decision script JSON."
    };
  }
}

function summarizeRuns(runs: ComputerUseRun[] | undefined) {
  const list = runs ?? [];
  let running = 0;
  let awaiting = 0;
  let completed = 0;
  list.forEach((run) => {
    const status = (run.status || "").toLowerCase();
    if (status.includes("running")) running += 1;
    if (status.includes("awaiting")) awaiting += 1;
    if (status.includes("completed")) completed += 1;
  });
  return {
    total: list.length,
    running,
    awaiting,
    completed
  };
}

function shortId(value?: string | null) {
  if (!value) return "";
  return value.slice(0, 8);
}

type TimelineEntry = {
  index: number;
  step: number | null;
  title: string;
  subtitle: string;
  kind: "call" | "output" | "policy" | "ack" | "other";
  item: ComputerUseTimelineItem;
};

function normalizeString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function isComputerUseSession(session: SandboxSession) {
  const purpose = typeof session.metadata?.purpose === "string" ? session.metadata.purpose : "";
  if (purpose.toLowerCase() === "computer_use") {
    return true;
  }
  const image = (session.image ?? "").toLowerCase();
  if (image.includes("computer-use")) {
    return true;
  }
  return session.image === defaultComputerUseImage;
}

function formatActionSummary(action: Record<string, unknown>) {
  const type = normalizeString(action.type).toLowerCase();
  if (!type) return "Action details unavailable";
  if (type === "visit_url") {
    return normalizeString(action.url) || "Navigate to URL";
  }
  if (type === "web_search") {
    const query = normalizeString(action.query);
    return query ? `Search: ${query}` : "Search the web";
  }
  if (type === "type") {
    const text = normalizeString(action.text);
    const hash = normalizeString(action.text_sha256);
    if (text === "[REDACTED]") {
      return hash ? `Typed text (redacted · ${hash.slice(0, 8)})` : "Typed text (redacted)";
    }
    return text ? `Typed: ${text}` : "Typed text";
  }
  if (type === "click" || type === "double_click") {
    const x = action.x;
    const y = action.y;
    if (typeof x === "number" && typeof y === "number") {
      return `Click at x:${x}, y:${y}`;
    }
    return "Click";
  }
  if (type === "scroll") {
    const dx = action.scroll_dx;
    const dy = action.scroll_dy;
    if (typeof dx === "number" || typeof dy === "number") {
      return `Scroll dx:${dx ?? 0}, dy:${dy ?? 0}`;
    }
    return "Scroll";
  }
  if (type === "keypress") {
    const keys = Array.isArray(action.keys) ? action.keys.join("+") : "";
    return keys ? `Keys: ${keys}` : "Keypress";
  }
  if (type === "wait") {
    const seconds = action.seconds;
    if (typeof seconds === "number") {
      return `Wait ${seconds}s`;
    }
    return "Wait";
  }
  if (type === "back") {
    return "Navigate back";
  }
  if (type === "terminate") {
    return "Terminate run";
  }
  return type.replace(/_/g, " ");
}

function buildTimelineEntries(items: ComputerUseTimelineItem[]): TimelineEntry[] {
  const entries: TimelineEntry[] = [];
  let stepCounter = 0;

  items.forEach((item, index) => {
    const type = normalizeString(item.type) || "event";
    let step = stepCounter + 1;
    let title = type.replace(/_/g, " ");
    let subtitle = "";
    let kind: TimelineEntry["kind"] = "other";

    if (type === "computer_call") {
      const action = (item.action ?? {}) as Record<string, unknown>;
      const actionType = normalizeString(action.type).replace(/_/g, " ") || "action";
      title = `Step ${step} Action · ${actionType}`;
      subtitle = formatActionSummary(action);
      kind = "call";
    } else if (type === "computer_call_output") {
      stepCounter += 1;
      step = stepCounter;
      const output = (item.output ?? {}) as Record<string, unknown>;
      const url = normalizeString(output.url);
      title = `Step ${step} Observation`;
      subtitle = url || "Observation captured";
      kind = "output";
    } else if (type === "policy_decision") {
      const decision = normalizeString(item.decision) || "decision";
      const checks = Array.isArray(item.checks) ? item.checks.length : 0;
      title = `Step ${step} Policy · ${decision.replace(/_/g, " ")}`;
      const reason = normalizeString(item.reason);
      subtitle = reason ? `Reason: ${reason}` : `${checks} checks`;
      kind = "policy";
    } else if (type === "acknowledged_safety_checks") {
      const decision = normalizeString(item.decision) || "decision";
      const acknowledged = Array.isArray(item.acknowledged) ? item.acknowledged.length : 0;
      title = `Step ${step} Approval · ${decision.replace(/_/g, " ")}`;
      subtitle = `${acknowledged} checks acknowledged`;
      kind = "ack";
    }

    entries.push({
      index,
      step: step || null,
      title,
      subtitle,
      kind,
      item
    });
  });

  return entries;
}

function findDefaultTimelineIndex(entries: TimelineEntry[]) {
  for (let idx = entries.length - 1; idx >= 0; idx -= 1) {
    if (entries[idx].kind === "output") {
      return idx;
    }
  }
  return entries.length - 1;
}

function timelineTone(kind: TimelineEntry["kind"]) {
  if (kind === "call") return "bg-indigo-500/15 text-indigo-200";
  if (kind === "output") return "bg-emerald-500/15 text-emerald-300";
  if (kind === "policy") return "bg-amber-500/15 text-amber-200";
  if (kind === "ack") return "bg-sky-500/15 text-sky-200";
  return "bg-muted/70 text-muted-foreground";
}

export default function ComputerUsePage() {
  const runsQuery = useComputerUseRuns();
  const runs = runsQuery.data ?? [];
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const runDetailQuery = useComputerUseRun(selectedRunId);
  const createRun = useCreateComputerUseRun();
  const acknowledgeRun = useAcknowledgeComputerUseRun();
  const sandboxSessionsQuery = useSandboxSessions();
  const [goal, setGoal] = useState("");
  const [allowedDomainsInput, setAllowedDomainsInput] = useState("");
  const [blockedDomainsInput, setBlockedDomainsInput] = useState("");
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>("on_risk");
  const [maxSteps, setMaxSteps] = useState("");
  const [maxRuntimeSeconds, setMaxRuntimeSeconds] = useState("");
  const [failureThreshold, setFailureThreshold] = useState("");
  const [decisionProvider, setDecisionProvider] = useState("scripted");
  const [decisionScript, setDecisionScript] = useState("");
  const [sandboxStrategy, setSandboxStrategy] = useState<SandboxStrategy>("new");
  const [sandboxSessionId, setSandboxSessionId] = useState("");
  const [sandboxMode, setSandboxMode] = useState<"docker" | "k8s">("docker");
  const [sandboxImage, setSandboxImage] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [scriptError, setScriptError] = useState<string | null>(null);
  const [acknowledgedChecks, setAcknowledgedChecks] = useState<string[]>([]);
  const [selectedEntryIndex, setSelectedEntryIndex] = useState<number | null>(null);
  const lastOutputIndexRef = useRef<number | null>(null);

  const allowedDomains = useMemo(
    () => parseDomainList(allowedDomainsInput),
    [allowedDomainsInput]
  );
  const blockedDomains = useMemo(
    () => parseDomainList(blockedDomainsInput),
    [blockedDomainsInput]
  );
  const summary = useMemo(() => summarizeRuns(runs), [runs]);
  const activeRun = useMemo(() => {
    if (runDetailQuery.data) return runDetailQuery.data;
    return runs.find((run) => run.id === selectedRunId) ?? null;
  }, [runDetailQuery.data, runs, selectedRunId]);
  const timelineQuery = useComputerUseTimeline(selectedRunId, {
    limit: 200,
    includeScreenshots: true,
    runStatus: activeRun?.status
  });
  const timelineItems = timelineQuery.data ?? [];
  const timelineEntries = useMemo(
    () => buildTimelineEntries(timelineItems),
    [timelineItems]
  );
  const latestOutputIndex = useMemo(
    () => findDefaultTimelineIndex(timelineEntries),
    [timelineEntries]
  );
  const pendingChecks = activeRun?.pending_checks ?? [];
  const availableSessions = useMemo(() => {
    return (sandboxSessionsQuery.data ?? []).filter((session) => {
      const status = (session.status || "").toLowerCase();
      if (!status.includes("ready") && !status.includes("starting")) {
        return false;
      }
      return isComputerUseSession(session);
    });
  }, [sandboxSessionsQuery.data]);

  useEffect(() => {
    if (!selectedRunId && runs.length > 0) {
      setSelectedRunId(runs[0].id);
    }
  }, [runs, selectedRunId]);

  useEffect(() => {
    setSelectedEntryIndex(null);
  }, [selectedRunId]);

  useEffect(() => {
    if (timelineEntries.length === 0) {
      setSelectedEntryIndex(null);
      lastOutputIndexRef.current = null;
      return;
    }
    if (
      selectedEntryIndex === null ||
      selectedEntryIndex >= timelineEntries.length ||
      selectedEntryIndex === lastOutputIndexRef.current
    ) {
      setSelectedEntryIndex(latestOutputIndex);
    }
    lastOutputIndexRef.current = latestOutputIndex;
  }, [latestOutputIndex, selectedEntryIndex, timelineEntries]);

  useEffect(() => {
    setAcknowledgedChecks([]);
  }, [activeRun?.id, pendingChecks.length]);

  const ackReady =
    pendingChecks.length === 0 ||
    pendingChecks.every((check) => acknowledgedChecks.includes(check.id));
  const selectedEntry =
    selectedEntryIndex !== null ? timelineEntries[selectedEntryIndex] : null;
  const selectedItem = selectedEntry?.item;
  const selectedOutput =
    selectedItem?.type === "computer_call_output" ? selectedItem.output : null;
  const selectedScreenshot =
    selectedOutput && typeof selectedOutput.screenshot_b64 === "string"
      ? selectedOutput.screenshot_b64
      : "";
  const selectedDetailRows = useMemo(() => {
    if (!selectedEntry || !selectedItem) return [];
    const rows: Array<{ label: string; value: string }> = [];
    if (selectedEntry.step) {
      rows.push({ label: "Step", value: String(selectedEntry.step) });
    }
    const callId = normalizeString(selectedItem.call_id);
    if (callId) {
      rows.push({ label: "Call ID", value: callId });
    }
    const type = normalizeString(selectedItem.type).replace(/_/g, " ");
    if (type) {
      rows.push({ label: "Item type", value: type });
    }

    if (selectedItem.type === "computer_call") {
      const action = (selectedItem.action ?? {}) as Record<string, unknown>;
      const actionType = normalizeString(action.type).replace(/_/g, " ");
      if (actionType) {
        rows.push({ label: "Action", value: actionType });
      }
      const summary = formatActionSummary(action);
      if (summary) {
        rows.push({ label: "Action detail", value: summary });
      }
    }
    if (selectedItem.type === "computer_call_output" && selectedOutput) {
      const url = normalizeString(selectedOutput.url);
      if (url) {
        rows.push({ label: "URL", value: url });
      }
      const execution = selectedOutput.execution ?? {};
      const status = normalizeString(execution.status);
      if (status) {
        rows.push({ label: "Execution", value: status });
      }
      const errorMessage = normalizeString(execution.error_message);
      if (errorMessage) {
        rows.push({ label: "Error", value: errorMessage });
      }
    }
    if (selectedItem.type === "policy_decision") {
      const decision = normalizeString(selectedItem.decision).replace(/_/g, " ");
      if (decision) {
        rows.push({ label: "Policy decision", value: decision });
      }
      const reason = normalizeString(selectedItem.reason);
      if (reason) {
        rows.push({ label: "Policy reason", value: reason });
      }
    }
    if (selectedItem.type === "acknowledged_safety_checks") {
      const decision = normalizeString(selectedItem.decision).replace(/_/g, " ");
      if (decision) {
        rows.push({ label: "Approval decision", value: decision });
      }
      const acknowledged = Array.isArray(selectedItem.acknowledged)
        ? selectedItem.acknowledged.length
        : 0;
      rows.push({ label: "Acknowledged checks", value: String(acknowledged) });
    }
    return rows;
  }, [selectedEntry, selectedItem, selectedOutput]);
  const selectedSafetyChecks = useMemo(() => {
    if (!selectedItem) return [];
    if (Array.isArray(selectedItem.checks)) {
      return selectedItem.checks;
    }
    if (Array.isArray(selectedItem.pending_safety_checks)) {
      return selectedItem.pending_safety_checks;
    }
    return [];
  }, [selectedItem]);

  const toggleCheck = (id: string, checked: boolean) => {
    setAcknowledgedChecks((current) => {
      if (checked) {
        return current.includes(id) ? current : [...current, id];
      }
      return current.filter((item) => item !== id);
    });
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    setScriptError(null);
    const trimmedGoal = goal.trim();
    if (!trimmedGoal) {
      setFormError("Goal is required.");
      return;
    }

    if (sandboxStrategy === "existing" && !sandboxSessionId.trim()) {
      setFormError("Select a sandbox session or switch to new session.");
      return;
    }

    const maxStepsParsed = parseOptionalInt(maxSteps, "Max steps");
    if (maxStepsParsed.error) {
      setFormError(maxStepsParsed.error);
      return;
    }
    const maxRuntimeParsed = parseOptionalInt(maxRuntimeSeconds, "Max runtime");
    if (maxRuntimeParsed.error) {
      setFormError(maxRuntimeParsed.error);
      return;
    }
    const failureParsed = parseOptionalInt(failureThreshold, "Failure threshold");
    if (failureParsed.error) {
      setFormError(failureParsed.error);
      return;
    }

    const scriptParsed = parseDecisionScript(decisionScript);
    if (scriptParsed.error) {
      setScriptError(scriptParsed.error);
      return;
    }

    const payload: CreateComputerUseRunInput = {
      goal: trimmedGoal,
      ...(allowedDomains.length ? { allowedDomains } : {}),
      ...(blockedDomains.length ? { blockedDomains } : {}),
      approvalMode,
      ...(maxStepsParsed.value ? { maxSteps: maxStepsParsed.value } : {}),
      ...(maxRuntimeParsed.value ? { maxRuntimeSeconds: maxRuntimeParsed.value } : {}),
      ...(failureParsed.value ? { failureThreshold: failureParsed.value } : {}),
      ...(decisionProvider.trim() ? { decisionProvider: decisionProvider.trim() } : {}),
      ...(scriptParsed.script ? { decisionScript: scriptParsed.script } : {})
    };

    if (sandboxStrategy === "existing") {
      payload.sandboxSessionId = sandboxSessionId.trim();
    } else {
      payload.sandboxMode = sandboxMode;
      if (sandboxImage.trim()) {
        payload.sandboxImage = sandboxImage.trim();
      }
    }

    createRun.mutate(payload, {
      onSuccess: (run) => {
        setSelectedRunId(run.id);
        setGoal("");
        setDecisionScript("");
        toast.success("Computer-use run started", {
          description: `Run ${shortId(run.id)} queued with ${run.status}.`
        });
      },
      onError: (error) => {
        const message = error instanceof Error ? error.message : "Unable to start run.";
        setFormError(message);
        toast.error("Run failed to start", { description: message });
      }
    });
  };

  const handleApprove = () => {
    if (!activeRun) return;
    acknowledgeRun.mutate(
      {
        id: activeRun.id,
        decision: "approve",
        acknowledged: acknowledgedChecks
      },
      {
        onSuccess: () => {
          toast.success("Safety checks acknowledged", {
            description: "The run will resume when the worker picks it up."
          });
        },
        onError: (error) => {
          const message = error instanceof Error ? error.message : "Unable to approve.";
          toast.error("Approval failed", { description: message });
        }
      }
    );
  };

  const handleDeny = () => {
    if (!activeRun) return;
    acknowledgeRun.mutate(
      {
        id: activeRun.id,
        decision: "deny",
        acknowledged: []
      },
      {
        onSuccess: () => {
          toast.info("Run denied", {
            description: "The run has been stopped."
          });
        },
        onError: (error) => {
          const message = error instanceof Error ? error.message : "Unable to deny.";
          toast.error("Deny failed", { description: message });
        }
      }
    );
  };

  return (
    <div className="relative z-10 mx-auto w-full max-w-[clamp(72rem,80vw,112rem)] space-y-8 px-4 py-8 text-zinc-100 sm:px-6 lg:px-10">
      <section className="home-card home-ring-soft rounded-3xl border border-white/10 bg-black/30 p-8 shadow-2xl shadow-indigo-500/15 backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="max-w-2xl">
            <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-indigo-200/80">
              Browser Computer-Use Mode
            </p>
            <h1 className="mt-2 text-3xl font-semibold text-white">
              Orchestrate safe browser runs
            </h1>
            <p className="mt-3 text-sm text-zinc-300">
              Observe, decide, gate, act, and trace each step with call IDs and
              approvals. Use scripted decisions today and swap providers later.
            </p>
          </div>
          <div className="grid w-full max-w-md gap-3 sm:grid-cols-3">
            <div className="rounded-2xl border border-white/10 bg-black/40 p-4 text-sm">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.3em] text-zinc-400">
                <MousePointerClick className="h-4 w-4" />
                Active
              </div>
              <p className="mt-2 text-2xl font-semibold text-white">{summary.running}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/40 p-4 text-sm">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.3em] text-zinc-400">
                <ShieldAlert className="h-4 w-4" />
                Awaiting
              </div>
              <p className="mt-2 text-2xl font-semibold text-white">{summary.awaiting}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/40 p-4 text-sm">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.3em] text-zinc-400">
                <CheckCircle2 className="h-4 w-4" />
                Completed
              </div>
              <p className="mt-2 text-2xl font-semibold text-white">{summary.completed}</p>
            </div>
          </div>
        </div>
      </section>

      <Card className="home-card home-ring-soft rounded-2xl border border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
        <CardHeader>
          <CardTitle className="text-lg font-semibold text-white">Launch a run</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <label
                className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400"
                htmlFor="computer-use-goal"
              >
                Goal
              </label>
              <Textarea
                id="computer-use-goal"
                rows={4}
                className={inputClassName}
                placeholder="Describe the browsing task and any guardrails..."
                value={goal}
                onChange={(event) => {
                  setGoal(event.target.value);
                  if (formError) setFormError(null);
                }}
                disabled={createRun.isPending}
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label
                  className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400"
                  htmlFor="allowed-domains"
                >
                  Allowed domains
                </label>
                <Textarea
                  id="allowed-domains"
                  rows={3}
                  className={inputClassName}
                  placeholder="example.com, docs.example.com"
                  value={allowedDomainsInput}
                  onChange={(event) => setAllowedDomainsInput(event.target.value)}
                  disabled={createRun.isPending}
                />
                {allowedDomains.length === 0 ? (
                  <p className="text-xs text-amber-200">
                    Allowlist is empty. The run will block navigation unless you add
                    domains or use "*".
                  </p>
                ) : (
                  <p className="text-xs text-zinc-400">
                    {allowedDomains.length} domain{allowedDomains.length === 1 ? "" : "s"} allowed.
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <label
                  className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400"
                  htmlFor="blocked-domains"
                >
                  Blocked domains
                </label>
                <Textarea
                  id="blocked-domains"
                  rows={3}
                  className={inputClassName}
                  placeholder="ads.example.com, tracking.example.org"
                  value={blockedDomainsInput}
                  onChange={(event) => setBlockedDomainsInput(event.target.value)}
                  disabled={createRun.isPending}
                />
                <p className="text-xs text-zinc-400">
                  Optional denylist applied after allowlist checks.
                </p>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <label
                  className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400"
                  htmlFor="approval-mode"
                >
                  Approval mode
                </label>
                <Select
                  value={approvalMode}
                  onValueChange={(value) => setApprovalMode(value as ApprovalMode)}
                >
                  <SelectTrigger id="approval-mode" className={selectTriggerClassName}>
                    <SelectValue placeholder="Select approval mode" />
                  </SelectTrigger>
                  <SelectContent className={selectContentClassName}>
                    {approvalModeOptions.map((option) => (
                      <SelectItem
                        key={option.value}
                        value={option.value}
                        className="rounded-lg px-2 py-2.5 text-sm text-zinc-100 data-[highlighted]:bg-indigo-500/20 data-[highlighted]:text-white"
                      >
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-zinc-400">
                  {approvalModeOptions.find((option) => option.value === approvalMode)?.helper}
                </p>
              </div>
              <div className="space-y-2">
                <label
                  className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400"
                  htmlFor="max-steps"
                >
                  Max steps
                </label>
                <Input
                  id="max-steps"
                  type="number"
                  min={1}
                  placeholder="25"
                  className={inputClassName}
                  value={maxSteps}
                  onChange={(event) => setMaxSteps(event.target.value)}
                  disabled={createRun.isPending}
                />
              </div>
              <div className="space-y-2">
                <label
                  className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400"
                  htmlFor="max-runtime"
                >
                  Max runtime (sec)
                </label>
                <Input
                  id="max-runtime"
                  type="number"
                  min={1}
                  placeholder="300"
                  className={inputClassName}
                  value={maxRuntimeSeconds}
                  onChange={(event) => setMaxRuntimeSeconds(event.target.value)}
                  disabled={createRun.isPending}
                />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label
                  className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400"
                  htmlFor="failure-threshold"
                >
                  Failure threshold
                </label>
                <Input
                  id="failure-threshold"
                  type="number"
                  min={1}
                  placeholder="3"
                  className={inputClassName}
                  value={failureThreshold}
                  onChange={(event) => setFailureThreshold(event.target.value)}
                  disabled={createRun.isPending}
                />
              </div>
              <div className="space-y-2">
                <label
                  className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400"
                  htmlFor="decision-provider"
                >
                  Decision provider
                </label>
                <Input
                  id="decision-provider"
                  placeholder="scripted"
                  className={inputClassName}
                  value={decisionProvider}
                  onChange={(event) => setDecisionProvider(event.target.value)}
                  disabled={createRun.isPending}
                />
                <p className="text-xs text-zinc-400">
                  Scripted is the only provider bundled today.
                </p>
              </div>
            </div>

            <div className="space-y-2">
              <label
                className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400"
                htmlFor="decision-script"
              >
                Decision script (JSON array)
              </label>
              <Textarea
                id="decision-script"
                rows={6}
                className={inputClassName}
                placeholder='[{"action":{"type":"visit_url","url":"https://example.com"}}]'
                value={decisionScript}
                onChange={(event) => {
                  setDecisionScript(event.target.value);
                  if (scriptError) setScriptError(null);
                }}
                disabled={createRun.isPending}
              />
              <p className="text-xs text-zinc-400">
                Leave empty to terminate immediately. Each entry should define a
                computer_call action.
              </p>
              {scriptError && <p className="text-sm text-destructive">{scriptError}</p>}
            </div>

            <div className="space-y-4 rounded-2xl border border-white/10 bg-black/40 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400">
                    Sandbox
                  </p>
                  <p className="text-xs text-zinc-400">
                    Choose a new isolated session or reuse an existing computer-use session.
                  </p>
                </div>
                <Clock className="h-4 w-4 text-zinc-400" />
              </div>
              <div className="space-y-2">
                <label
                  className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400"
                  htmlFor="sandbox-strategy"
                >
                  Session strategy
                </label>
                <Select
                  value={sandboxStrategy}
                  onValueChange={(value) => setSandboxStrategy(value as SandboxStrategy)}
                >
                  <SelectTrigger id="sandbox-strategy" className={selectTriggerClassName}>
                    <SelectValue placeholder="Select strategy" />
                  </SelectTrigger>
                  <SelectContent className={selectContentClassName}>
                    <SelectItem
                      value="new"
                      className="rounded-lg px-2 py-2.5 text-sm text-zinc-100 data-[highlighted]:bg-indigo-500/20 data-[highlighted]:text-white"
                    >
                      Create new session
                    </SelectItem>
                    <SelectItem
                      value="existing"
                      className="rounded-lg px-2 py-2.5 text-sm text-zinc-100 data-[highlighted]:bg-indigo-500/20 data-[highlighted]:text-white"
                    >
                      Use existing session
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {sandboxStrategy === "existing" ? (
                <div className="space-y-3">
                  <div className="space-y-2">
                    <label
                      className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400"
                      htmlFor="sandbox-session-id"
                    >
                      Sandbox session ID
                    </label>
                    <Input
                      id="sandbox-session-id"
                      placeholder="Session UUID"
                      className={inputClassName}
                      value={sandboxSessionId}
                      onChange={(event) => setSandboxSessionId(event.target.value)}
                      disabled={createRun.isPending}
                    />
                  </div>
                  {availableSessions.length > 0 ? (
                    <div className="flex flex-wrap gap-2 text-xs text-zinc-400">
                      {availableSessions.map((session) => (
                        <Button
                          key={session.id}
                          type="button"
                          variant="outline"
                          size="sm"
                          className="rounded-full border-white/20 text-zinc-200"
                          onClick={() => setSandboxSessionId(session.id)}
                        >
                          {shortId(session.id)} · {session.status}
                        </Button>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-zinc-400">
                      No active computer-use sessions available. Start a new session instead.
                    </p>
                  )}
                  <p className="text-[11px] text-zinc-500">
                    Only sessions created with the computer-use image are listed.
                  </p>
                </div>
              ) : (
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <label
                      className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400"
                      htmlFor="sandbox-mode"
                    >
                      Sandbox mode
                    </label>
                    <Select
                      value={sandboxMode}
                      onValueChange={(value) => setSandboxMode(value as "docker" | "k8s")}
                    >
                      <SelectTrigger id="sandbox-mode" className={selectTriggerClassName}>
                        <SelectValue placeholder="Select mode" />
                      </SelectTrigger>
                      <SelectContent className={selectContentClassName}>
                        <SelectItem
                          value="docker"
                          className="rounded-lg px-2 py-2.5 text-sm text-zinc-100 data-[highlighted]:bg-indigo-500/20 data-[highlighted]:text-white"
                        >
                          Docker
                        </SelectItem>
                        <SelectItem
                          value="k8s"
                          className="rounded-lg px-2 py-2.5 text-sm text-zinc-100 data-[highlighted]:bg-indigo-500/20 data-[highlighted]:text-white"
                        >
                          Kubernetes
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <label
                      className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400"
                      htmlFor="sandbox-image"
                    >
                      Sandbox image (optional)
                    </label>
                    <Input
                      id="sandbox-image"
                      placeholder="astraforge/computer-use:latest"
                      className={inputClassName}
                      value={sandboxImage}
                      onChange={(event) => setSandboxImage(event.target.value)}
                      disabled={createRun.isPending}
                    />
                  </div>
                </div>
              )}
            </div>

            {formError && <p className="text-sm text-destructive">{formError}</p>}

            <div className="flex flex-wrap items-center gap-3">
              <Button
                type="submit"
                variant="brand"
                className="rounded-xl"
                disabled={createRun.isPending}
              >
                {createRun.isPending ? "Launching..." : "Start run"}
              </Button>
              <p className="text-xs text-zinc-400">
                Runs are executed asynchronously in the computer-use worker.
              </p>
            </div>
          </form>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <Card className="home-card home-ring-soft rounded-2xl border border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
          <CardHeader className="space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <CardTitle className="text-lg font-semibold text-white">
                  Conversation history
                </CardTitle>
                <p className="text-xs text-zinc-400">
                  Timeline events for the selected run, including past requests.
                </p>
              </div>
              <div className="w-full max-w-[260px] space-y-2">
                <label
                  className="text-[10px] font-semibold uppercase tracking-[0.3em] text-zinc-400"
                  htmlFor="computer-use-run-select"
                >
                  Run
                </label>
                <Select
                  value={selectedRunId ?? ""}
                  onValueChange={(value) => setSelectedRunId(value)}
                  disabled={runsQuery.isLoading || runs.length === 0}
                >
                  <SelectTrigger id="computer-use-run-select" className={selectTriggerClassName}>
                    <SelectValue placeholder="Select a run" />
                  </SelectTrigger>
                  <SelectContent className={selectContentClassName}>
                    {runs.map((run) => (
                      <SelectItem
                        key={run.id}
                        value={run.id}
                        className="rounded-lg px-2 py-2.5 text-sm text-zinc-100 data-[highlighted]:bg-indigo-500/20 data-[highlighted]:text-white"
                      >
                        Run {shortId(run.id)} · {formatStatusLabel(run.status)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {runsQuery.isLoading ? (
              <div className="space-y-3">
                {[...Array(4)].map((_, index) => (
                  <div key={index} className="h-20 rounded-2xl bg-white/5" />
                ))}
              </div>
            ) : runsQuery.isError ? (
              <div className="rounded-2xl border border-white/10 bg-black/20 p-4 text-sm text-destructive">
                Unable to load runs right now.
              </div>
            ) : runs.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-white/10 bg-black/20 p-6 text-center text-sm text-zinc-400">
                No computer-use runs yet. Launch a new run to get started.
              </div>
            ) : timelineQuery.isError ? (
              <div className="rounded-2xl border border-white/10 bg-black/20 p-4 text-sm text-destructive">
                Unable to load timeline events for this run.
              </div>
            ) : timelineQuery.isLoading ? (
              <div className="space-y-3">
                {[...Array(5)].map((_, index) => (
                  <div key={index} className="h-16 rounded-2xl bg-white/5" />
                ))}
              </div>
            ) : timelineEntries.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-white/10 bg-black/20 p-6 text-center text-sm text-zinc-400">
                No timeline items yet. The run may still be initializing.
              </div>
            ) : (
              <ul className="space-y-3">
                {timelineEntries.map((entry) => {
                  const isSelected = entry.index === selectedEntryIndex;
                  return (
                    <li key={`${entry.index}-${entry.kind}`}>
                      <button
                        type="button"
                        onClick={() => setSelectedEntryIndex(entry.index)}
                        className={cn(
                          "w-full rounded-2xl border px-4 py-3 text-left shadow-sm transition",
                          isSelected
                            ? "border-indigo-400/60 bg-indigo-500/10"
                            : "border-white/10 bg-black/20 hover:-translate-y-0.5 hover:border-indigo-400/40"
                        )}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="min-w-0 space-y-1">
                            <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-zinc-400">
                              Step {entry.step ?? "-"}
                            </p>
                            <p className="text-sm font-semibold text-white">{entry.title}</p>
                            {entry.subtitle ? (
                              <p className="text-xs text-zinc-400">{entry.subtitle}</p>
                            ) : null}
                          </div>
                          <Badge
                            className={cn(
                              "rounded-full px-2.5 py-0.5 text-[10px] uppercase",
                              timelineTone(entry.kind)
                            )}
                          >
                            {entry.kind.replace(/_/g, " ")}
                          </Badge>
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card className="home-card home-ring-soft rounded-2xl border border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
          <CardHeader>
            <CardTitle className="text-lg font-semibold text-white">Preview</CardTitle>
            <p className="text-xs text-zinc-400">
              Event detail, screenshots, and approvals for the selected run.
            </p>
          </CardHeader>
          <CardContent>
            {!activeRun ? (
              <div className="rounded-2xl border border-dashed border-white/10 bg-black/20 p-6 text-center text-sm text-zinc-400">
                Select a run to inspect its progress.
              </div>
            ) : (
              <div className="space-y-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <Badge
                    className={cn(
                      "rounded-full px-3 py-1 text-[11px]",
                      statusTone(activeRun.status)
                    )}
                  >
                    {formatStatusLabel(activeRun.status)}
                  </Badge>
                  <div className="text-xs text-zinc-400">
                    Updated {formatTimestamp(activeRun.updated_at)}
                  </div>
                </div>

                <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-zinc-400">
                    Goal
                  </p>
                  <p className="mt-2 text-sm text-zinc-200">{activeRun.goal}</p>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-zinc-400">
                      Step
                    </p>
                    <p className="mt-2 text-sm text-zinc-200">{activeRun.step_index ?? 0}</p>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-zinc-400">
                      Stop reason
                    </p>
                    <p className="mt-2 text-sm text-zinc-200">
                      {activeRun.stop_reason ? formatStatusLabel(activeRun.stop_reason) : "None"}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-zinc-400">
                      Sandbox session
                    </p>
                    <p className="mt-2 break-all text-sm text-zinc-200">
                      {activeRun.sandbox_session_id ?? "Auto-provisioned"}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-zinc-400">
                      Trace directory
                    </p>
                    <p className="mt-2 break-all text-sm text-zinc-200">
                      {activeRun.trace_dir || "Pending"}
                    </p>
                  </div>
                </div>

                <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-zinc-400">
                    Selected event
                  </p>
                  {selectedEntry ? (
                    <div className="mt-2 space-y-3">
                      <div>
                        <p className="text-sm font-semibold text-white">{selectedEntry.title}</p>
                        {selectedEntry.subtitle ? (
                          <p className="text-xs text-zinc-400">{selectedEntry.subtitle}</p>
                        ) : null}
                      </div>
                      {selectedDetailRows.length > 0 ? (
                        <div className="space-y-2 text-xs text-zinc-300">
                          {selectedDetailRows.map((row) => (
                            <div
                              key={row.label}
                              className="flex flex-wrap items-start justify-between gap-3"
                            >
                              <span className="uppercase tracking-[0.2em] text-zinc-500">
                                {row.label}
                              </span>
                              <span className="max-w-[70%] break-all text-zinc-200">
                                {row.value}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : null}
                      {selectedSafetyChecks.length > 0 ? (
                        <div className="space-y-2">
                          {selectedSafetyChecks.map((check) => (
                            <div
                              key={check.id}
                              className="flex items-start gap-2 rounded-lg border border-white/10 bg-black/30 p-2 text-xs"
                            >
                              <Badge
                                className={cn(
                                  "rounded-full px-2 py-0.5 text-[10px] uppercase",
                                  severityTone(check.severity)
                                )}
                              >
                                {check.severity}
                              </Badge>
                              <div>
                                <p className="text-[10px] uppercase tracking-[0.3em] text-zinc-400">
                                  {check.category}
                                </p>
                                <p className="text-xs text-zinc-200">{check.message}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <p className="mt-2 text-sm text-zinc-400">
                      Select a timeline item to preview the details.
                    </p>
                  )}
                </div>

                <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-zinc-400">
                    Screenshot
                  </p>
                  {selectedEntry?.kind === "output" && selectedScreenshot ? (
                    <div className="mt-3 overflow-hidden rounded-xl border border-white/10 bg-black/40">
                      <img
                        src={`data:image/png;base64,${selectedScreenshot}`}
                        alt="Run step screenshot"
                        className="h-auto w-full"
                      />
                    </div>
                  ) : (
                    <p className="mt-2 text-sm text-zinc-400">
                      No screenshot available for this event.
                    </p>
                  )}
                </div>

                {activeRun.status === "awaiting_ack" ? (
                  <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 space-y-4">
                    <div className="flex items-center gap-2 text-amber-200">
                      <AlertTriangle className="h-4 w-4" />
                      <p className="text-sm font-semibold">Approval required</p>
                    </div>
                    {pendingChecks.length === 0 ? (
                      <p className="text-sm text-amber-200">
                        No explicit checks were returned, but the policy still requires acknowledgement.
                      </p>
                    ) : (
                      <div className="space-y-3">
                        {pendingChecks.map((check) => {
                          const checked = acknowledgedChecks.includes(check.id);
                          return (
                            <div
                              key={check.id}
                              className="flex items-start gap-3 rounded-xl border border-amber-500/20 bg-black/20 p-3"
                            >
                              <Checkbox
                                id={`check-${check.id}`}
                                checked={checked}
                                onCheckedChange={(value) =>
                                  toggleCheck(check.id, Boolean(value))
                                }
                              />
                              <div className="space-y-1">
                                <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-[0.3em] text-amber-200/80">
                                  <Badge
                                    className={cn(
                                      "rounded-full px-2 py-0.5 text-[10px]",
                                      severityTone(check.severity)
                                    )}
                                  >
                                    {check.severity}
                                  </Badge>
                                  <span>{check.category}</span>
                                </div>
                                <p className="text-sm text-amber-100">{check.message}</p>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    <div className="flex flex-wrap items-center gap-3">
                      <Button
                        type="button"
                        variant="brand"
                        className="rounded-xl"
                        onClick={handleApprove}
                        disabled={!ackReady || acknowledgeRun.isPending}
                      >
                        {acknowledgeRun.isPending ? "Submitting..." : "Approve and resume"}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        className="rounded-xl border-amber-200/40 text-amber-100"
                        onClick={handleDeny}
                        disabled={acknowledgeRun.isPending}
                      >
                        Deny run
                      </Button>
                    </div>
                    {!ackReady ? (
                      <p className="text-xs text-amber-200">
                        Acknowledge all checks before approving.
                      </p>
                    ) : null}
                  </div>
                ) : (
                  <div className="rounded-2xl border border-white/10 bg-black/20 p-4 text-sm text-zinc-400">
                    {activeRun.status === "running" ? (
                      <div className="flex items-center gap-2">
                        <Clock className="h-4 w-4" />
                        <span>Run is active. New steps will appear in the trace.</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="h-4 w-4" />
                        <span>Run is not awaiting approval.</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
