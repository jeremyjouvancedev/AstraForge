import axios from "axios";
import { ChangeEvent, FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "@/lib/auth";
import { submitEarlyAccessRequest } from "@/lib/api-client";

const heroTags = [
  "Isolation by default",
  "Explicit permissions",
  "Artifacts & diffs",
  "Replayable runs",
  "API / MCP-ready"
];

const policyItems = [
  { label: "Network", value: "ALLOW: github.com", accent: "text-emerald-300" },
  { label: "Filesystem", value: "/workspace (rw)" },
  { label: "Secrets", value: "scoped", accent: "text-amber-300" },
  { label: "Limits", value: "2 vCPU · 4GB · 10m" }
];

const artifactItems = [
  { label: "report.md", value: "generated", accent: "text-cyan-300" },
  { label: "patch.diff", value: "ready", accent: "text-fuchsia-300" },
  { label: "logs.jsonl", value: "streaming" },
  { label: "metrics.json", value: "captured" }
];

const productCards = [
  {
    title: "Sandbox packages",
    description: "Ready-to-use templates (Python/Node/Bash/custom) with policies, runtimes, and limits.",
    bullets: ["Versioned runtime", "Controlled filesystem", "Network allowlist", "Time/CPU/RAM caps"]
  },
  {
    title: "Execution contracts",
    description: "Every run is a contract: inputs, allowed tools, logs, artifacts, exit codes.",
    bullets: ["Typed parameters", "Explicit permissions", "Tool wrappers", "Verifiable outputs"]
  },
  {
    title: "Artifacts & replay",
    description: "No artifacts, no serious agent. AstraForge captures everything for inspection and replay.",
    bullets: ["Diffs / patches", "Reports (md/pdf)", "Logs & traces", "Replayable runs"]
  }
];

const architecturePillars = [
  {
    title: "Control plane",
    description: "Templates, policies, secrets, versioning, approvals."
  },
  {
    title: "Execution plane",
    description: "Isolated sandboxes, resource limits, deterministic runtimes."
  },
  {
    title: "Agent interface",
    description: "I/O contracts, event streaming, orchestrator integration."
  },
  {
    title: "Artifact layer",
    description: "Logs, diffs, reports, metrics, storage & retention."
  }
];

const executionFlow = [
  {
    title: "1) Define sandbox",
    subtitle: "template + policy",
    description: "Runtime + permissions + limits + tool allowlist."
  },
  {
    title: "2) Execute DeepAgent",
    subtitle: "stream events",
    description: "Wrapped actions, complete logs, controlled outputs."
  },
  {
    title: "3) Inspect artifacts",
    subtitle: "diffs + reports",
    description: "Human verification, approvals, replayability."
  },
  {
    title: "4) Replay & iterate",
    subtitle: "versioned",
    description: "Runs become assets: reproducible, shareable, governable."
  }
];

const securityPills = [
  "Isolation by default",
  "Network allowlist",
  "Scoped secrets",
  "Audit logs",
  "Policy-as-code",
  "Replayable runs"
];

const securityCards = [
  {
    title: "Explicit permissions",
    description: "Every capability (FS, network, tools, secrets) is declared."
  },
  {
    title: "Full observability",
    description: "Logs, traces, exit codes, artifacts — for audit and debugging."
  },
  {
    title: "Reproducibility",
    description: "Versioned runtimes + controlled inputs → replayable runs."
  }
];

const pricingPlans = [
  {
    name: "Trial",
    price: "Free",
    description: "Validate first value fast.",
    badge: "Start here",
    badgeTone: "neutral",
    features: ["Limited templates", "Execution quota", "Short log retention"],
    cta: "Join waitlist"
  },
  {
    name: "Pro",
    price: "Usage-based",
    description: "For teams moving to production.",
    badge: "Most popular",
    badgeTone: "primary",
    features: ["Unlimited sandboxes", "Full observability", "Artifacts & replay", "Quotas & guardrails"],
    cta: "Request access",
    highlighted: true
  },
  {
    name: "Enterprise",
    price: "Custom",
    description: "Security, compliance, integrations, advanced governance.",
    badge: "On-prem / air-gapped",
    badgeTone: "neutral",
    features: ["On-prem / private cloud", "Policies & approvals", "SSO / RBAC", "SLAs + support"],
    cta: "Talk to us"
  }
];

const faqItems = [
  {
    question: "Does AstraForge replace an agent orchestrator?",
    answer:
      "No. AstraForge provides the execution environment (sandboxes) and run contracts. It integrates with your orchestrator/framework."
  },
  {
    question: "Why not just Docker / Kubernetes?",
    answer:
      "Because agents need policies, logs, artifacts, I/O contracts, explicit permissions, and replayability — all designed agent-first."
  },
  {
    question: "What’s auditable?",
    answer:
      "Actions, logs, inputs, outputs, artifacts, exit codes, metrics — and the policy that allowed each capability."
  },
  {
    question: "How do you handle secrets?",
    answer:
      "Scoped secrets (least privilege), optional rotation, controlled exposure at runtime — never globally accessible."
  }
];

const waitlistTags = [
  "DeepAgent-ready",
  "Artifacts & replay",
  "Policies & limits",
  "Enterprise-friendly"
];

const glowTopStyle = {
  background:
    "radial-gradient(circle at 30% 30%, rgba(99,102,241,.35), transparent 55%), radial-gradient(circle at 70% 50%, rgba(168,85,247,.28), transparent 60%), radial-gradient(circle at 50% 80%, rgba(34,211,238,.18), transparent 60%)"
};

const glowBottomStyle = {
  background:
    "radial-gradient(circle at 45% 40%, rgba(99,102,241,.18), transparent 60%), radial-gradient(circle at 60% 60%, rgba(168,85,247,.16), transparent 60%)"
};

export default function HomePage() {
  const { isAuthenticated, authSettings } = useAuth();
  const billingEnabled = authSettings?.billing_enabled ?? true;
  const waitlistActive = Boolean(authSettings?.waitlist_enabled && !authSettings?.allow_all_users);
  const primaryCtaHref = isAuthenticated ? "/app" : waitlistActive ? "#waitlist" : "/register";
  const primaryCtaLabel = isAuthenticated ? "Open console" : waitlistActive ? "Request access" : "Get started";
  const currentYear = new Date().getFullYear();
  const [waitlistForm, setWaitlistForm] = useState({
    email: "",
    teamRole: "",
    projectSummary: ""
  });
  const [waitlistSubmitting, setWaitlistSubmitting] = useState(false);
  const [waitlistFeedback, setWaitlistFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const handleWaitlistChange =
    (field: "email" | "teamRole" | "projectSummary") =>
    (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      setWaitlistForm((prev) => ({ ...prev, [field]: event.target.value }));
      setWaitlistFeedback(null);
    };

  const handleWaitlistSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!waitlistForm.email) {
      setWaitlistFeedback({ type: "error", text: "Please add your work email so we can reach you." });
      return;
    }
    setWaitlistSubmitting(true);
    try {
      const result = await submitEarlyAccessRequest({
        email: waitlistForm.email,
        teamRole: waitlistForm.teamRole,
        projectSummary: waitlistForm.projectSummary
      });
      setWaitlistFeedback({
        type: "success",
        text: result.owner_email_sent
          ? "You're on the list! Check your inbox for a confirmation email."
          : "You're confirmed! Check your inbox for a confirmation email. We couldn't ping the team automatically, but we'll follow up shortly."
      });
      setWaitlistForm({ email: "", teamRole: "", projectSummary: "" });
    } catch (err) {
      console.error(err);
      setWaitlistFeedback({
        type: "error",
        text:
          axios.isAxiosError(err) && typeof err.response?.data?.detail === "string"
            ? err.response.data.detail
            : "We couldn't submit your request. Please try again in a moment."
      });
    } finally {
      setWaitlistSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 antialiased" style={{ colorScheme: "dark" }}>
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute inset-0 home-noise opacity-30" />
        <div className="absolute inset-0 home-grid opacity-30" />

        <div
          className="absolute -top-40 left-1/2 h-[520px] w-[820px] -translate-x-1/2 rounded-full blur-3xl"
          style={glowTopStyle}
        />
        <div
          className="absolute -bottom-56 left-1/2 h-[520px] w-[920px] -translate-x-1/2 rounded-full blur-3xl"
          style={glowBottomStyle}
        />
      </div>

      <header className="relative z-10">
        <nav className="mx-auto flex max-w-[clamp(75rem,85vw,112rem)] items-center justify-between px-6 py-6">
          <Link to="/" className="flex items-center gap-3">
            <div
              className="h-9 w-9 rounded-xl home-ring-soft home-glow"
              style={{
                background:
                  "radial-gradient(circle at 30% 30%, rgba(99,102,241,1), rgba(168,85,247,1))"
              }}
            />
            <div className="leading-tight">
              <div className="text-sm font-semibold tracking-wide">AstraForge</div>
              <div className="text-xs text-zinc-400">Sandbox factory for DeepAgents</div>
            </div>
          </Link>

          <div className="hidden items-center gap-7 text-sm text-zinc-300 md:flex">
            <a href="#product" className="hover:text-white">
              Product
            </a>
            <a href="#architecture" className="hover:text-white">
              Architecture
            </a>
            <a href="#security" className="hover:text-white">
              Security
            </a>
            <a href="#pricing" className="hover:text-white">
              Pricing
            </a>
            <a href="#faq" className="hover:text-white">
              FAQ
            </a>
          </div>

          <div className="flex items-center gap-3">
            <a
              href="#demo"
              className="hidden rounded-xl px-4 py-2 text-sm text-zinc-300 ring-1 ring-white/10 hover:bg-white/5 md:inline-flex"
            >
              View an example
            </a>
            {isAuthenticated ? (
              <Link
                to="/app"
                className="inline-flex rounded-xl px-4 py-2 text-sm font-semibold text-white home-btn-primary ring-1 ring-white/10"
              >
                Open console
              </Link>
            ) : (
              <a
                href={primaryCtaHref}
                className="inline-flex rounded-xl px-4 py-2 text-sm font-semibold text-white home-btn-primary ring-1 ring-white/10"
              >
                {primaryCtaLabel}
              </a>
            )}
          </div>
        </nav>
      </header>

      <main className="relative z-10">
        <section className="mx-auto max-w-[clamp(75rem,85vw,112rem)] px-6 pt-10 pb-16 md:pt-16">
          <div className="grid items-center gap-12 md:grid-cols-2">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full bg-white/5 px-3 py-1 text-xs text-zinc-300 ring-1 ring-white/10">
                <span className="h-2 w-2 rounded-full bg-emerald-400" />
                Production-grade execution for autonomous agents
              </div>

              <h1 className="mt-6 text-4xl font-semibold tracking-tight md:text-5xl">
                Secure, auditable <span className="text-indigo-300">sandboxes</span>
                <br />
                where <span className="text-cyan-300">DeepAgents</span> execute real work.
              </h1>

              <p className="mt-5 text-base leading-relaxed text-zinc-300 md:text-lg">
                AstraForge is a <span className="text-zinc-100">sandbox factory</span>: isolation, explicit permissions,
                full logs, verifiable artifacts, replayable runs.
                <span className="text-zinc-100"> Agents get hands.</span> You keep the keys.
              </p>

              <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
                <a
                  href={primaryCtaHref}
                  className="inline-flex items-center justify-center rounded-xl px-5 py-3 text-sm font-semibold text-white home-btn-primary ring-1 ring-white/10"
                >
                  {primaryCtaLabel}
                </a>
                <a
                  href="#demo"
                  className="inline-flex items-center justify-center rounded-xl px-5 py-3 text-sm font-semibold text-zinc-200 ring-1 ring-white/10 hover:bg-white/5"
                >
                  See how it works
                </a>
              </div>

              <div className="mt-6 flex flex-wrap items-center gap-2 text-xs text-zinc-400">
                {heroTags.map((tag) => (
                  <span key={tag} className="home-tag rounded-full px-3 py-1">
                    {tag}
                  </span>
                ))}
              </div>
            </div>

            <div className="floaty">
              <div className="home-card home-ring-soft rounded-2xl p-5 md:p-6">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold">Sandbox Execution — Live Trace</div>
                  <div className="flex items-center gap-2 text-xs text-zinc-400">
                    <span className="inline-flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-emerald-400" /> running
                    </span>
                  </div>
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <div className="rounded-xl bg-black/30 p-4 ring-1 ring-white/10">
                    <div className="text-xs text-zinc-400">Policy</div>
                    <div className="mt-2 space-y-2 text-sm">
                      {policyItems.map((item) => (
                        <div key={item.label} className="flex items-center justify-between">
                          <span className="text-zinc-200">{item.label}</span>
                          <span className={item.accent ?? "text-zinc-300"}>{item.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-xl bg-black/30 p-4 ring-1 ring-white/10">
                    <div className="text-xs text-zinc-400">Artifacts</div>
                    <div className="mt-2 space-y-2 text-sm">
                      {artifactItems.map((item) => (
                        <div key={item.label} className="flex items-center justify-between">
                          <span className="text-zinc-200">{item.label}</span>
                          <span className={item.accent ?? "text-zinc-300"}>{item.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="mt-4 rounded-xl bg-black/40 p-4 ring-1 ring-white/10">
                  <div className="flex items-center justify-between">
                    <div className="text-xs text-zinc-400">Command log</div>
                    <div className="flex items-center gap-2 text-xs text-zinc-500">
                      <span className="home-kbd rounded-lg px-2 py-1">Ctrl</span>
                      <span className="home-kbd rounded-lg px-2 py-1">K</span>
                      <span>Run</span>
                    </div>
                  </div>
                  <pre className="mt-3 overflow-x-auto text-xs leading-relaxed text-zinc-300">
                    <code>{`$ git clone repo
$ deepagent plan --task "audit + patch"
$ python -m pytest
$ generate artifact patch.diff
✔ exit_code=0  duration=128s`}</code>
                  </pre>
                </div>

                <div className="mt-4 flex items-center justify-between text-xs text-zinc-400">
                  <div>Reproducible · Auditable · Safe execution</div>
                  <a href="#demo" className="text-zinc-200 hover:text-white">
                    Open example →
                  </a>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-[clamp(75rem,85vw,112rem)] px-6 pb-10">
          <div className="home-card home-ring-soft rounded-2xl px-6 py-5">
            <div className="grid gap-4 md:grid-cols-4 md:items-center">
              <div className="md:col-span-1">
                <div className="text-sm font-semibold">Built for serious teams</div>
                <div className="text-xs text-zinc-400">Platform · Infra · AI Engineering</div>
              </div>
              <div className="grid gap-3 sm:grid-cols-3 md:col-span-3">
                <div className="rounded-xl bg-black/30 p-4 ring-1 ring-white/10">
                  <div className="text-xs text-zinc-400">Outcome</div>
                  <div className="mt-2 text-sm text-zinc-200">Agents that execute safely</div>
                </div>
                <div className="rounded-xl bg-black/30 p-4 ring-1 ring-white/10">
                  <div className="text-xs text-zinc-400">Control</div>
                  <div className="mt-2 text-sm text-zinc-200">Explicit permissions & limits</div>
                </div>
                <div className="rounded-xl bg-black/30 p-4 ring-1 ring-white/10">
                  <div className="text-xs text-zinc-400">Trust</div>
                  <div className="mt-2 text-sm text-zinc-200">Logs + artifacts you can audit</div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="product" className="mx-auto max-w-[clamp(75rem,85vw,112rem)] px-6 py-16">
          <div className="max-w-4xl">
            <h2 className="text-3xl font-semibold tracking-tight">
              AstraForge provides the execution layer for DeepAgents
            </h2>
            <p className="mt-4 text-zinc-300">
              DeepAgents can plan. AstraForge gives them a controlled environment to act: isolation, governance,
              observability, replayability.
            </p>
          </div>

          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {productCards.map((card) => (
              <div key={card.title} className="home-card home-ring-soft rounded-2xl p-6">
                <div className="text-sm font-semibold">{card.title}</div>
                <p className="mt-2 text-sm text-zinc-300">{card.description}</p>
                <ul className="mt-4 space-y-2 text-sm text-zinc-300">
                  {card.bullets.map((bullet) => (
                    <li key={bullet}>• {bullet}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        <section id="architecture" className="mx-auto max-w-[clamp(75rem,85vw,112rem)] px-6 py-16">
          <div className="grid gap-10 md:grid-cols-2 md:items-start">
            <div>
              <h2 className="text-3xl font-semibold tracking-tight">
                Architecture designed for agent-first execution
              </h2>
              <p className="mt-4 text-zinc-300">
                AstraForge cleanly separates the <span className="text-zinc-100">control plane</span> from the
                <span className="text-zinc-100"> execution plane</span>, then exposes an agent-facing interface
                (API/MCP/events) with a dedicated artifact layer.
              </p>

              <div className="mt-6 grid gap-3">
                {architecturePillars.map((pillar) => (
                  <div key={pillar.title} className="rounded-2xl bg-black/30 p-5 ring-1 ring-white/10">
                    <div className="text-sm font-semibold">{pillar.title}</div>
                    <p className="mt-1 text-sm text-zinc-300">{pillar.description}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="home-card home-ring-soft rounded-2xl p-6">
              <div className="text-sm font-semibold">Execution flow</div>
              <p className="mt-2 text-sm text-zinc-300">AstraForge runs are inspectable end to end.</p>

              <div className="mt-5 space-y-3 text-sm">
                {executionFlow.map((step) => (
                  <div key={step.title} className="rounded-xl bg-black/35 p-4 ring-1 ring-white/10">
                    <div className="flex items-center justify-between">
                      <span className="text-zinc-200">{step.title}</span>
                      <span className="text-xs text-zinc-400">{step.subtitle}</span>
                    </div>
                    <p className="mt-2 text-xs text-zinc-400">{step.description}</p>
                  </div>
                ))}
              </div>

              <div className="mt-6 rounded-xl bg-black/40 p-4 ring-1 ring-white/10">
                <div className="text-xs text-zinc-400">Core promise</div>
                <div className="mt-2 text-sm text-zinc-200">
                  “Agents can act — <span className="text-zinc-100">safely</span>, with{" "}
                  <span className="text-zinc-100">full auditability</span>.”
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="security" className="mx-auto max-w-[clamp(75rem,85vw,112rem)] px-6 py-16">
          <div className="home-card home-ring-soft rounded-2xl p-8 md:p-10">
            <div className="grid gap-10 md:grid-cols-2 md:items-center">
              <div>
                <h2 className="text-3xl font-semibold tracking-tight">Security & governance by design</h2>
                <p className="mt-4 text-zinc-300">
                  AstraForge never executes anything “silently”. Everything is explicit: permissions, limits, outputs.
                  Built for platform, infra, and security teams.
                </p>

                <div className="mt-6 flex flex-wrap gap-2 text-xs text-zinc-300">
                  {securityPills.map((pill) => (
                    <span key={pill} className="home-tag rounded-full px-3 py-1">
                      {pill}
                    </span>
                  ))}
                </div>
              </div>

              <div className="grid gap-4">
                {securityCards.map((card) => (
                  <div key={card.title} className="rounded-2xl bg-black/35 p-5 ring-1 ring-white/10">
                    <div className="text-sm font-semibold">{card.title}</div>
                    <p className="mt-2 text-sm text-zinc-300">{card.description}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="demo" className="mx-auto max-w-[clamp(75rem,85vw,112rem)] px-6 py-16">
          <div className="grid gap-10 md:grid-cols-2 md:items-start">
            <div>
              <h2 className="text-3xl font-semibold tracking-tight">A concrete example</h2>
              <p className="mt-4 text-zinc-300">
                Typical use-case: a DeepAgent audits a repo, proposes a patch, runs tests, and produces a report — all
                inside a governed sandbox.
              </p>

              <div className="mt-6 rounded-2xl bg-black/35 p-5 text-sm text-zinc-300 ring-1 ring-white/10">
                <div className="mb-2 text-xs text-zinc-400">What you get</div>
                <ul className="space-y-2">
                  <li>
                    • <span className="text-zinc-100">patch.diff</span> (exact changes)
                  </li>
                  <li>
                    • <span className="text-zinc-100">report.md</span> (analysis + recommendations)
                  </li>
                  <li>
                    • <span className="text-zinc-100">test output</span> (proof)
                  </li>
                  <li>
                    • <span className="text-zinc-100">logs.jsonl</span> (full audit trail)
                  </li>
                </ul>
              </div>
            </div>

            <div className="home-card home-ring-soft rounded-2xl p-6">
              <div className="text-sm font-semibold">Example run</div>
              <p className="mt-2 text-sm text-zinc-300">Input → Execution → Artifacts.</p>
              <div className="mt-4 rounded-xl bg-black/45 p-4 ring-1 ring-white/10">
                <pre className="overflow-x-auto text-xs leading-relaxed text-zinc-200">
                  <code>
{`{
  "sandbox": "deepagent-repo-audit@v1.3",
  "inputs": {
    "repo": "github.com/org/service",
    "task": "security audit + patch",
    "constraints": ["no outbound except allowlist", "max_runtime=10m"]
  },
  "permissions": {
    "network": ["github.com", "pypi.org"],
    "filesystem": ["/workspace:rw"],
    "secrets": ["READONLY_TOKEN:scoped"]
  },
  "outputs": ["report.md", "patch.diff", "logs.jsonl", "metrics.json"]
}`}
                  </code>
                </pre>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl bg-black/35 p-4 ring-1 ring-white/10">
                  <div className="text-xs text-zinc-400">Result</div>
                  <div className="mt-2 text-sm text-emerald-300">exit_code: 0</div>
                  <div className="mt-1 text-xs text-zinc-400">duration: 128s</div>
                </div>
                <div className="rounded-xl bg-black/35 p-4 ring-1 ring-white/10">
                  <div className="text-xs text-zinc-400">Artifacts</div>
                  <div className="mt-2 text-sm text-zinc-200">4 files generated</div>
                  <div className="mt-1 text-xs text-zinc-400">diff + report + logs</div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {billingEnabled ? (
          <section id="pricing" className="mx-auto max-w-[clamp(75rem,85vw,112rem)] px-6 py-16">
            <div className="max-w-2xl">
              <h2 className="text-3xl font-semibold tracking-tight">Pricing built around execution</h2>
              <p className="mt-4 text-zinc-300">
                AstraForge isn’t priced on hype. You pay for controlled compute, reliable sandboxes, and the governance
                required for production agents.
              </p>
            </div>

            <div className="mt-10 grid gap-5 md:grid-cols-3">
              {pricingPlans.map((plan) => (
                <div
                  key={plan.name}
                  className={`home-card home-ring-soft rounded-2xl p-7 ${
                    plan.highlighted ? "border border-white/20" : ""
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-semibold">{plan.name}</div>
                    <span
                      className={`rounded-full px-3 py-1 text-xs ${
                        plan.badgeTone === "primary"
                          ? "home-btn-primary text-white ring-1 ring-white/10"
                          : "home-tag text-zinc-300"
                      }`}
                    >
                      {plan.badge}
                    </span>
                  </div>
                  <div className="mt-3 text-3xl font-semibold">{plan.price}</div>
                  <p className="mt-2 text-sm text-zinc-300">{plan.description}</p>
                  <ul className="mt-5 space-y-2 text-sm text-zinc-300">
                    {plan.features.map((feature) => (
                      <li key={feature}>• {feature}</li>
                    ))}
                  </ul>
                  <a
                    href="#waitlist"
                    className={`mt-6 inline-flex w-full items-center justify-center rounded-xl px-4 py-2 text-sm font-semibold ${
                      plan.highlighted
                        ? "text-white home-btn-primary ring-1 ring-white/10"
                        : "text-zinc-200 ring-1 ring-white/10 hover:bg-white/5"
                    }`}
                  >
                    {plan.cta}
                  </a>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <section id="faq" className="mx-auto max-w-[clamp(75rem,85vw,112rem)] px-6 py-16">
          <div className="max-w-2xl">
            <h2 className="text-3xl font-semibold tracking-tight">FAQ</h2>
            <p className="mt-4 text-zinc-300">Questions we typically get when agents “actually execute”.</p>
          </div>

          <div className="mt-10 grid gap-5 md:grid-cols-2">
            {faqItems.map((item) => (
              <div key={item.question} className="home-card home-ring-soft rounded-2xl p-6">
                <div className="text-sm font-semibold">{item.question}</div>
                <p className="mt-2 text-sm text-zinc-300">{item.answer}</p>
              </div>
            ))}
          </div>
        </section>

        {!isAuthenticated && (
          <section id="waitlist" className="mx-auto max-w-[clamp(75rem,85vw,112rem)] px-6 pb-20">
            <div className="home-card home-ring-soft rounded-2xl p-8 md:p-10">
              {waitlistActive ? (
                <div className="grid gap-8 md:grid-cols-2 md:items-center">
                  <div>
                    <h2 className="text-3xl font-semibold tracking-tight">Request early access</h2>
                    <p className="mt-3 text-zinc-300">
                      We prioritize teams building DeepAgents in real conditions (repos, scripts, ops, data tasks). We’ll get
                      back quickly with a demo.
                    </p>
                    <div className="mt-5 flex flex-wrap gap-2 text-xs text-zinc-300">
                      {waitlistTags.map((tag) => (
                        <span key={tag} className="home-tag rounded-full px-3 py-1">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>

                  <form className="rounded-2xl bg-black/35 p-6 ring-1 ring-white/10" onSubmit={handleWaitlistSubmit}>
                    <div className="text-sm font-semibold">Join the waitlist</div>
                    <p className="mt-1 text-xs text-zinc-400">No spam. Just product updates & access.</p>

                    <div className="mt-4 space-y-3">
                      <label className="block">
                        <span className="text-xs text-zinc-400">Work email</span>
                        <input
                          type="email"
                          required
                          placeholder="name@company.com"
                          className="mt-1 w-full rounded-xl bg-black/40 px-4 py-3 text-sm text-zinc-100 ring-1 ring-white/10 placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-indigo-400/50"
                          value={waitlistForm.email}
                          onChange={handleWaitlistChange("email")}
                        />
                      </label>

                      <label className="block">
                        <span className="text-xs text-zinc-400">Team / role</span>
                        <input
                          type="text"
                          placeholder="Platform · Infra · AI Engineering"
                          className="mt-1 w-full rounded-xl bg-black/40 px-4 py-3 text-sm text-zinc-100 ring-1 ring-white/10 placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-indigo-400/50"
                          value={waitlistForm.teamRole}
                          onChange={handleWaitlistChange("teamRole")}
                        />
                      </label>

                      <label className="block">
                        <span className="text-xs text-zinc-400">What are you building?</span>
                        <textarea
                          rows={3}
                          placeholder="DeepAgents that patch repos, run tasks, and produce artifacts…"
                          className="mt-1 w-full rounded-xl bg-black/40 px-4 py-3 text-sm text-zinc-100 ring-1 ring-white/10 placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-indigo-400/50"
                          value={waitlistForm.projectSummary}
                          onChange={handleWaitlistChange("projectSummary")}
                        />
                      </label>

                      {waitlistFeedback ? (
                        <p
                          className={`text-xs ${
                            waitlistFeedback.type === "success" ? "text-emerald-300" : "text-rose-300"
                          }`}
                          aria-live="polite"
                        >
                          {waitlistFeedback.text}
                        </p>
                      ) : null}

                      <button
                        type="submit"
                        className="mt-2 inline-flex w-full items-center justify-center rounded-xl px-5 py-3 text-sm font-semibold text-white home-btn-primary ring-1 ring-white/10 disabled:opacity-60"
                        disabled={waitlistSubmitting}
                      >
                        {waitlistSubmitting ? "Submitting..." : "Request access"}
                      </button>
                    </div>
                  </form>
                </div>
              ) : (
                <div className="flex flex-col items-center py-10 text-center">
                  <h2 className="text-4xl font-semibold tracking-tight">Ready to deploy your first DeepAgent?</h2>
                  <p className="mt-4 max-w-2xl text-lg text-zinc-300">
                    Provision secure sandboxes, replay runs, and ship with confidence. AstraForge is ready for production.
                  </p>
                  <Link
                    to="/register"
                    className="mt-10 inline-flex items-center justify-center rounded-2xl px-10 py-4 text-lg font-semibold text-white home-btn-primary ring-1 ring-white/10"
                  >
                    Create your account
                  </Link>
                  <p className="mt-6 text-sm text-zinc-500">
                    Already have an account?{" "}
                    <Link to="/login" className="text-indigo-300 hover:text-white">
                      Sign in
                    </Link>
                  </p>
                </div>
              )}
            </div>
          </section>
        )}
      </main>

      <footer className="relative z-10 border-t border-white/10">
        <div className="mx-auto max-w-[clamp(75rem,85vw,112rem)] px-6 py-10">
          <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-3">
              <div
                className="h-8 w-8 rounded-xl home-ring-soft home-glow"
                style={{
                  background:
                    "radial-gradient(circle at 30% 30%, rgba(99,102,241,1), rgba(168,85,247,1))"
                }}
              />
              <div>
                <div className="text-sm font-semibold">AstraForge</div>
                <div className="text-xs text-zinc-500">Production-grade sandboxes for DeepAgents</div>
              </div>
            </div>

            <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-zinc-400">
              <a href="#product" className="hover:text-white">
                Product
              </a>
              <a href="#architecture" className="hover:text-white">
                Architecture
              </a>
              <a href="#security" className="hover:text-white">
                Security
              </a>
              <a href="#pricing" className="hover:text-white">
                Pricing
              </a>
              <a href="#faq" className="hover:text-white">
                FAQ
              </a>
            </div>
          </div>

          <div className="mt-8 flex flex-col gap-2 text-xs text-zinc-600 md:flex-row md:items-center md:justify-between">
            <div>© {currentYear} AstraForge. All rights reserved.</div>
            <div className="flex gap-4">
              <a href="#security" className="hover:text-zinc-300">
                Security
              </a>
              <a href="#" className="hover:text-zinc-300">
                Privacy
              </a>
              <a href="#" className="hover:text-zinc-300">
                Terms
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
