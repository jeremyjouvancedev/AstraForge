import type { FormEvent } from "react";
import { useMemo, useState } from "react";
import { Clock, ChevronDown, ChevronUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  LLMSelectionFields,
  LLMProvider,
  ReasoningEffort
} from "@/features/chat/components/llm-selection-fields";
import { useSandboxSessions } from "@/features/sandbox/hooks/use-sandbox-sessions";
import { type CreateComputerUseRunInput, type SandboxSession } from "@/lib/api-client";
import { cn } from "@/lib/utils";

type ApprovalMode = "auto" | "on_risk" | "always";
type SandboxStrategy = "new" | "existing";

const approvalModeOptions: Array<{ value: ApprovalMode; label: string; helper: string }> = [
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
    const normalized = parsed.map((item: unknown) => {
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

function shortId(value?: string | null) {
  if (!value) return "";
  return value.slice(0, 8);
}

const defaultBrowserUseImage = "astraforge/computer-use:latest";

function isBrowserUseSession(session: SandboxSession) {
  const purpose = typeof session.metadata?.purpose === "string" ? session.metadata.purpose : "";
  if (purpose.toLowerCase() === "computer_use") {
    return true;
  }
  const image = (session.image ?? "").toLowerCase();
  if (image.includes("computer-use")) {
    return true;
  }
  return session.image === defaultBrowserUseImage;
}

interface ComputerUseSetupProps {
  onSubmit: (payload: CreateComputerUseRunInput) => void;
  isPending: boolean;
}

export function ComputerUseSetup({ onSubmit, isPending }: ComputerUseSetupProps) {
  const [goal, setGoal] = useState("");
  const [llmProvider, setLlmProvider] = useState<LLMProvider>("ollama");
  const [llmModel, setLlmModel] = useState("devstral-small-2:24b");
  const [reasoningCheck, setReasoningCheck] = useState(false);
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>("high");

  // Optional / Advanced fields
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [allowedDomainsInput, setAllowedDomainsInput] = useState("*");
  const [blockedDomainsInput, setBlockedDomainsInput] = useState("");
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>("on_risk");
  const [maxSteps, setMaxSteps] = useState("");
  const [maxRuntimeSeconds, setMaxRuntimeSeconds] = useState("");
  const [failureThreshold, setFailureThreshold] = useState("");
  const [decisionProvider, setDecisionProvider] = useState("deepagent");
  const [decisionScript, setDecisionScript] = useState("");
  const [sandboxStrategy, setSandboxStrategy] = useState<SandboxStrategy>("new");
  const [sandboxSessionId, setSandboxSessionId] = useState("");
  const [sandboxMode, setSandboxMode] = useState<"docker" | "k8s">("docker");
  const [sandboxImage, setSandboxImage] = useState("");

  const [formError, setFormError] = useState<string | null>(null);
  const [scriptError, setScriptError] = useState<string | null>(null);

  const sandboxSessionsQuery = useSandboxSessions();
  const availableSessions = useMemo(() => {
    return (sandboxSessionsQuery.data ?? []).filter((session) => {
      const status = (session.status || "").toLowerCase();
      if (!status.includes("ready") && !status.includes("starting")) {
        return false;
      }
      return isBrowserUseSession(session);
    });
  }, [sandboxSessionsQuery.data]);

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

    const allowedDomains = parseDomainList(allowedDomainsInput);
    const blockedDomains = parseDomainList(blockedDomainsInput);

    const payload: CreateComputerUseRunInput = {
      goal: trimmedGoal,
      ...(allowedDomains.length ? { allowedDomains } : {}),
      ...(blockedDomains.length ? { blockedDomains } : {}),
      approvalMode,
      ...(maxStepsParsed.value ? { maxSteps: maxStepsParsed.value } : {}),
      ...(maxRuntimeParsed.value ? { maxRuntimeSeconds: maxRuntimeParsed.value } : {}),
      ...(failureParsed.value ? { failureThreshold: failureParsed.value } : {}),
      ...(decisionProvider.trim() ? { decisionProvider: decisionProvider.trim() } : {}),
      ...(scriptParsed.script ? { decisionScript: scriptParsed.script } : {}),
      llmProvider,
      llmModel,
      reasoningCheck,
      reasoningEffort
    };

    if (sandboxStrategy === "existing") {
      payload.sandboxSessionId = sandboxSessionId.trim();
    } else {
      payload.sandboxMode = sandboxMode;
      if (sandboxImage.trim()) {
        payload.sandboxImage = sandboxImage.trim();
      }
    }

    onSubmit(payload);
  };

  return (
    <Card className="mx-auto w-full max-w-3xl home-card home-ring-soft rounded-3xl border border-white/10 bg-black/30 text-zinc-100 shadow-2xl shadow-indigo-500/15 backdrop-blur">
      <CardHeader>
        <CardTitle className="text-2xl font-semibold text-white">Start a Browser-Use Run</CardTitle>
        <p className="text-sm text-zinc-400">Define your goal and choose a model to begin.</p>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-8">
          <div className="space-y-3">
            <label
              className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400"
              htmlFor="browser-use-goal"
            >
              What is your goal?
            </label>
            <Textarea
              id="browser-use-goal"
              rows={4}
              className={cn(inputClassName, "text-base py-4")}
              placeholder="e.g., Navigate to example.com and find the contact email..."
              value={goal}
              onChange={(event) => {
                setGoal(event.target.value);
                if (formError) setFormError(null);
              }}
              disabled={isPending}
            />
          </div>

          <div className="space-y-4">
            <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400">
              Model Selection
            </label>
            <div className="rounded-2xl border border-white/5 bg-white/5 p-5">
              <LLMSelectionFields
                provider={llmProvider}
                onProviderChange={(val) => setLlmProvider(val as LLMProvider)}
                model={llmModel}
                onModelChange={setLlmModel}
                reasoningCheck={reasoningCheck}
                onReasoningCheckChange={setReasoningCheck}
                reasoningEffort={reasoningEffort}
                onReasoningEffortChange={setReasoningEffort}
                disabled={isPending}
              />
            </div>
          </div>

          <div className="pt-2">
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              {showAdvanced ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              {showAdvanced ? "Hide Optional Settings" : "Show Optional Settings"}
            </button>
          </div>

          {showAdvanced && (
            <div className="space-y-8 animate-in fade-in slide-in-from-top-4 duration-300">
              <div className="grid gap-6 md:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400">
                    Allowed domains
                  </label>
                  <Input
                    className={inputClassName}
                    placeholder="*, example.com"
                    value={allowedDomainsInput}
                    onChange={(e) => setAllowedDomainsInput(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400">
                    Blocked domains
                  </label>
                  <Input
                    className={inputClassName}
                    placeholder="ads.com"
                    value={blockedDomainsInput}
                    onChange={(e) => setBlockedDomainsInput(e.target.value)}
                  />
                </div>
              </div>

              <div className="grid gap-6 md:grid-cols-2">
                <div className="space-y-2">
                   <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400">
                     Decision provider
                   </label>
                   <Select
                     value={decisionProvider}
                     onValueChange={(value) => setDecisionProvider(value)}
                   >
                     <SelectTrigger className={selectTriggerClassName}>
                       <SelectValue />
                     </SelectTrigger>
                     <SelectContent className={selectContentClassName}>
                       <SelectItem value="deepagent">DeepAgent (LLM)</SelectItem>
                       <SelectItem value="scripted">Scripted (JSON)</SelectItem>
                     </SelectContent>
                   </Select>
                </div>
                {decisionProvider === "scripted" && (
                   <div className="space-y-2">
                    <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400">
                      Decision script
                    </label>
                    <Textarea
                      className={inputClassName}
                      rows={4}
                      placeholder='[{"action": {"type": "visit_url", "url": "..."}}]'
                      value={decisionScript}
                      onChange={(e) => setDecisionScript(e.target.value)}
                    />
                    {scriptError && <p className="text-xs text-destructive">{scriptError}</p>}
                  </div>
                )}
              </div>

              <div className="grid gap-6 md:grid-cols-3">
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400">
                    Approval mode
                  </label>
                  <Select
                    value={approvalMode}
                    onValueChange={(value) => setApprovalMode(value as ApprovalMode)}
                  >
                    <SelectTrigger className={selectTriggerClassName}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className={selectContentClassName}>
                      {approvalModeOptions.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400">
                    Max steps
                  </label>
                  <Input
                    type="number"
                    className={inputClassName}
                    value={maxSteps}
                    onChange={(e) => setMaxSteps(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400">
                    Max runtime (s)
                  </label>
                  <Input
                    type="number"
                    className={inputClassName}
                    value={maxRuntimeSeconds}
                    onChange={(e) => setMaxRuntimeSeconds(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-6">
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400">
                    Failure threshold
                  </label>
                  <Input
                    type="number"
                    className={inputClassName}
                    value={failureThreshold}
                    onChange={(e) => setFailureThreshold(e.target.value)}
                  />
                </div>

                <div className="space-y-4 rounded-2xl border border-white/10 bg-black/40 p-5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400">Sandbox Strategy</span>
                    <Clock className="h-4 w-4 text-zinc-500" />
                  </div>
                  <Select
                    value={sandboxStrategy}
                    onValueChange={(value) => setSandboxStrategy(value as SandboxStrategy)}
                  >
                    <SelectTrigger className={selectTriggerClassName}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className={selectContentClassName}>
                      <SelectItem value="new">Create new session</SelectItem>
                      <SelectItem value="existing">Use existing session</SelectItem>
                    </SelectContent>
                  </Select>

                  {sandboxStrategy === "existing" ? (
                    <div className="space-y-3 pt-2">
                      <Input
                        placeholder="Session UUID"
                        className={inputClassName}
                        value={sandboxSessionId}
                        onChange={(event) => setSandboxSessionId(event.target.value)}
                      />
                      {availableSessions.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                          {availableSessions.map((s) => (
                            <Button
                              key={s.id}
                              type="button"
                              variant="outline"
                              size="sm"
                              className="rounded-full border-white/10 bg-white/5 text-[10px]"
                              onClick={() => setSandboxSessionId(s.id)}
                            >
                              {shortId(s.id)}
                            </Button>
                          ))}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="grid gap-4 md:grid-cols-2 pt-2">
                      <div className="space-y-2">
                        <label className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">Mode</label>
                        <Select value={sandboxMode} onValueChange={(val: "docker" | "k8s") => setSandboxMode(val)}>
                           <SelectTrigger className={selectTriggerClassName}>
                              <SelectValue />
                           </SelectTrigger>
                           <SelectContent className={selectContentClassName}>
                              <SelectItem value="docker">Docker</SelectItem>
                              <SelectItem value="k8s">Kubernetes</SelectItem>
                           </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2">
                        <label className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">Image (Optional)</label>
                        <Input
                          className={inputClassName}
                          value={sandboxImage}
                          onChange={(e) => setSandboxImage(e.target.value)}
                          placeholder="astraforge/computer-use:latest"
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {formError && <p className="text-sm text-destructive">{formError}</p>}

          <Button
            type="submit"
            variant="brand"
            className="w-full py-6 text-lg font-semibold rounded-2xl shadow-xl shadow-indigo-500/20"
            disabled={isPending}
          >
            {isPending ? "Starting Run..." : "Start Run"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}