// src/features/marketing/pages/home-page.tsx

import { Link } from "react-router-dom";
import {
  ActivitySquare,
  ArrowRight,
  Bolt,
  Boxes,
  Brain,
  CheckCircle,
  Command,
  GitBranch,
  Globe2,
  HardDriveDownload,
  Layers,
  Shield,
  Sparkles,
  Terminal,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useAuth } from "@/lib/auth";

/**
 * DATA
 */
const capabilities = [
  {
    title: "Safe agent execution at scale",
    description:
      "Run DeepAgent, Codex, or any coding CLI inside hardened Docker/K8s sandboxes with read-only roots, dropped caps, and controlled egress.",
    icon: Shield,
  },
  {
    title: "Translate specs to code",
    description:
      "Feed a natural-language spec to an agent; it writes, tests, and prepares a merge-ready patch inside the sandbox.",
    icon: Terminal,
  },
  {
    title: "Background remediation",
    description:
      "Wire error streams to trigger Codex workspaces that reproduce, patch, and propose an MR without manual triage (Sentry/Glitchtip incoming).",
    icon: Bolt,
  },
  {
    title: "Visibility and trust",
    description:
      "Every command, diff, artifact, and chat event is streamed and persisted, so reviewers see exactly what ran.",
    icon: ActivitySquare,
  },
  {
    title: "Long-running LLM work",
    description:
      "Offload intermediate state and artifacts to secure sandboxes instead of stuffing everything into the LLM context.",
    icon: HardDriveDownload,
  },
  {
    title: "Context offloading",
    description:
      "Agents persist checkpoints, files, and logs to the sandbox filesystem so long tasks stay performant.",
    icon: Boxes,
  },
];

const tracks = [
  {
    title: "Coding Sandboxes",
    description:
      "Codex CLI and other coding CLIs run in isolated workspaces to translate specs into code, patch bugs, and prep merge requests.",
    icon: Command,
  },
  {
    title: "DeepAgent Backend",
    description:
      "Hosted LangChain DeepAgent runtime with the same sandbox guarantees for conversational and agentic flows.",
    icon: Brain,
  },
];

const happyPath = [
  { title: "Capture", description: "Prompt or alert received via UI, API, or webhook.", icon: Sparkles },
  { title: "Provision", description: "Spin up Codex/CLI or DeepAgent sandbox on Docker/K8s.", icon: Layers },
  { title: "Execute", description: "Agent reads spec, edits code, runs tests, creates patch.", icon: Terminal },
  { title: "Stream", description: "Real-time logs, diffs, chat, and artifacts via SSE.", icon: Globe2 },
  { title: "Ship", description: "Review MR-quality output and merge with confidence.", icon: CheckCircle },
];

const audiences = [
  {
    title: "SRE / Incident Response",
    description:
      "Auto-reproduce errors (Sentry/Glitchtip webhook support incoming) in a sandbox, validate the fix, and ship the MR with full run history.",
    icon: Bolt,
  },
  {
    title: "Platform / Infra",
    description:
      "Safely run agents that evolve Terraform, Helm, or CI with repo/path allowlists and audit trails.",
    icon: Layers,
  },
  {
    title: "Product Engineering",
    description:
      "Capture intent as a prompt, let the agent code in a sandbox, then review diffs/tests before merge.",
    icon: GitBranch,
  },
  {
    title: "AI / Agent Engineers",
    description:
      "Run DeepAgent or custom AI agents at scale with consistent isolation, egress controls, and replayable runs.",
    icon: Brain,
  },
];

const stackColumns = [
  {
    title: "Backend",
    items: ["Django + DRF", "Celery Workers", "Redis Streams", "Postgres (+pgvector)", "S3 / MinIO Artifacts"],
  },
  {
    title: "Frontend",
    items: ["Vite + React Query", "shadcn/ui", "SSE Streaming (Live)", "Diff Viewers"],
  },
  {
    title: "Sandboxing",
    items: ["Docker / Kubernetes", "Seccomp / Read-only roots", "Idle / TTL Reaping", "Snapshots"],
  },
];

/**
 * UI helpers
 */
function SectionHeader({
  eyebrow,
  title,
  subtitle,
  center = true,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  center?: boolean;
}) {
  return (
    <div className={center ? "text-center" : ""}>
      <p className="text-xs font-semibold uppercase tracking-[0.35em] text-muted-foreground">{eyebrow}</p>
      <h2 className="mt-2 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">{title}</h2>
      {subtitle ? (
        <p className="mx-auto mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground sm:text-base">{subtitle}</p>
      ) : null}
    </div>
  );
}

function FeatureCard({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <Card className="group relative h-full overflow-hidden rounded-2xl border bg-background/70 shadow-sm backdrop-blur transition-all hover:-translate-y-0.5 hover:shadow-lg">
      {/* hover glow */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity group-hover:opacity-100"
        style={{
          background:
            "radial-gradient(800px circle at 20% 10%, rgba(61,110,255,0.10), transparent 40%), radial-gradient(700px circle at 80% 30%, rgba(16,185,129,0.08), transparent 45%)",
        }}
      />
      <CardContent className="relative space-y-3 p-5">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary ring-1 ring-primary/10">
          <Icon className="h-5 w-5" />
        </div>
        <div className="space-y-1">
          <p className="text-base font-semibold tracking-tight">{title}</p>
          <p className="text-sm leading-relaxed text-muted-foreground">{description}</p>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * PAGE
 */
export default function HomePage() {
  const { isAuthenticated } = useAuth();
  const primaryCta = isAuthenticated ? "/app" : "/register";

  return (
    <div className="relative min-h-screen bg-background text-foreground">
      {/* softer, more “premium” background */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          background:
            "radial-gradient(circle at 15% 10%, rgba(61,110,255,0.12), transparent 32%), radial-gradient(circle at 85% 0%, rgba(16,185,129,0.10), transparent 34%), radial-gradient(circle at 45% 90%, rgba(99,102,241,0.08), transparent 36%)",
        }}
      />

      {/* header */}
      <header className="sticky top-0 z-30 border-b bg-background/70 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary ring-1 ring-primary/10">
              <Sparkles className="h-5 w-5" />
            </div>
            <div className="leading-tight">
              <p className="text-base font-semibold tracking-tight">AstraForge</p>
              <p className="text-[10px] uppercase tracking-[0.35em] text-muted-foreground">Agent Sandboxing</p>
            </div>
          </div>

          <nav className="hidden items-center gap-5 text-sm font-medium text-muted-foreground sm:flex">
            <a href="#capabilities" className="transition hover:text-foreground">
              Capabilities
            </a>
            <a href="#tracks" className="transition hover:text-foreground">
              Tracks
            </a>
            <a href="#workflow" className="transition hover:text-foreground">
              Workflow
            </a>
            <a href="#stack" className="transition hover:text-foreground">
              Stack
            </a>
          </nav>

          <div className="flex items-center gap-2">
            <Button asChild size="sm" variant="ghost" className="rounded-xl">
              <Link to="/login">Login</Link>
            </Button>
            <Button asChild size="sm" className="rounded-xl">
              <Link to={primaryCta}>{isAuthenticated ? "Open console" : "Get access"}</Link>
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto flex max-w-6xl flex-col gap-16 px-5 pb-20 pt-10 sm:px-8 sm:pt-14">
        {/* hero */}
        <section className="relative overflow-hidden rounded-3xl border bg-background/70 px-6 py-10 shadow-xl backdrop-blur sm:px-10">
          <div
            aria-hidden
            className="absolute inset-0 -z-10"
            style={{
              background:
                "linear-gradient(135deg, rgba(61,110,255,0.10) 0%, rgba(16,185,129,0.07) 45%, transparent 80%)",
            }}
          />

          <div className="mx-auto flex max-w-3xl flex-col items-center text-center">
            <Badge variant="secondary" className="rounded-full px-4 py-2 text-[11px] uppercase tracking-[0.3em]">
              Production-ready agent sandboxing
            </Badge>

            <h1 className="mt-6 text-4xl font-semibold tracking-tight sm:text-5xl">
              Safe agent sandboxing <span className="text-muted-foreground">that ships real code.</span>
            </h1>

            <p className="mt-4 text-base leading-relaxed text-muted-foreground sm:text-lg">
              AstraForge runs coding agents inside hardened Docker/K8s sandboxes—turning specs or production alerts
              into observable, merge-ready patches.
            </p>

            <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
              <Button asChild size="lg" className="rounded-full px-6">
                <Link to={primaryCta} className="inline-flex items-center gap-2">
                  {isAuthenticated ? "Start building" : "Get access"} <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline" className="rounded-full px-6">
                <a href="#stack">Read documentation</a>
              </Button>
            </div>

            {/* terminal preview */}
            <div className="relative mt-10 w-full overflow-hidden rounded-3xl border bg-slate-950 text-slate-50 shadow-2xl">
              <div className="flex items-center justify-between border-b border-white/10 px-4 py-3 text-xs">
                <span className="uppercase tracking-[0.25em] text-slate-300">
                  $ astraforge-agent --sandbox-id=dev-82x --mode=remediate
                </span>
                <span className="hidden rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[10px] text-slate-300 sm:inline-flex">
                  streamed • persisted
                </span>
              </div>
              <div className="p-5">
                <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-slate-200">
{`$ initializing sandbox environment...
✓ provisioned k8s-pod/agent-runner-01 (150ms)
✓ mounted read-only rootfs
✓ network policy: egress-allow-list applied

$ agent connecting to repo...
Analyzing src/backend/api.ts... found 2 issues

$ generating fix...
- const timeout = 1000;
+ const timeout = config.get('API_TIMEOUT_MS') || 5000;

$ running tests...
PASS src/backend/api.test.ts

— awaiting approval for merge request #42`}
                </pre>
              </div>
            </div>
          </div>
        </section>

        {/* capabilities */}
        <section id="capabilities" className="space-y-8">
          <SectionHeader
            eyebrow="Core capabilities"
            title="Run agents safely—at one sandbox or hundreds."
            subtitle="Isolation, observability, and reproducibility built in. Reviewers see exactly what ran."
          />
          <div className="grid gap-5 md:grid-cols-3">
            {capabilities.map((item) => (
              <FeatureCard key={item.title} icon={item.icon} title={item.title} description={item.description} />
            ))}
          </div>
        </section>

        {/* tracks */}
        <section id="tracks" className="rounded-3xl border bg-background/70 p-6 shadow-lg backdrop-blur sm:p-8">
          <SectionHeader
            eyebrow="Two clear tracks"
            title="CLI power or managed agent runtime."
            subtitle="Same sandbox guarantees. Pick the execution mode that fits your workflow."
          />

          <div className="mt-8 grid gap-6 lg:grid-cols-[1.05fr,0.95fr] lg:items-stretch">
            <div className="space-y-4">
              {tracks.map((track) => {
                const Icon = track.icon;
                return (
                  <Card key={track.title} className="rounded-2xl border bg-muted/40 shadow-sm">
                    <CardHeader className="pb-2">
                      <CardTitle className="flex items-center gap-3 text-base">
                        <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/10 text-primary ring-1 ring-primary/10">
                          <Icon className="h-5 w-5" />
                        </span>
                        {track.title}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="pt-0 text-sm leading-relaxed text-muted-foreground">{track.description}</CardContent>
                  </Card>
                );
              })}
            </div>

            <div className="relative overflow-hidden rounded-3xl border bg-slate-950 p-7 text-slate-50 shadow-2xl">
              <div
                aria-hidden
                className="absolute inset-0 opacity-70"
                style={{
                  background:
                    "radial-gradient(900px circle at 20% 15%, rgba(61,110,255,0.22), transparent 40%), radial-gradient(700px circle at 90% 25%, rgba(16,185,129,0.16), transparent 45%)",
                }}
              />
              <div className="relative">
                <p className="text-xs font-semibold uppercase tracking-[0.25em] text-slate-300">
                  Secure Container Runtime (Docker/K8s)
                </p>

                <div className="mt-6 grid grid-cols-2 gap-4">
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
                    <p className="text-[11px] uppercase tracking-[0.25em] text-slate-300">Spec to Code</p>
                    <p className="mt-2 text-lg font-semibold">Codex CLI</p>
                    <p className="mt-2 text-xs leading-relaxed text-slate-300">Translate specs, patch bugs, prep MRs.</p>
                  </div>

                  <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
                    <p className="text-[11px] uppercase tracking-[0.25em] text-slate-300">Reasoning Engine</p>
                    <p className="mt-2 text-lg font-semibold">DeepAgent</p>
                    <p className="mt-2 text-xs leading-relaxed text-slate-300">Conversational/agentic flows with sandbox parity.</p>
                  </div>
                </div>

                <div className="mt-6 flex flex-wrap gap-2">
                  {["Sandbox TTL", "Seccomp", "Snapshots", "Egress allowlist", "Audit log"].map((t) => (
                    <span key={t} className="rounded-full border border-white/10 bg-white/5 px-3 py-2 text-[11px] text-slate-200">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* workflow */}
        <section id="workflow" className="rounded-3xl border bg-background/70 p-6 shadow-lg backdrop-blur sm:p-8">
          <SectionHeader
            eyebrow="Happy path execution"
            title="From capture to merge—with full transparency."
            subtitle="A predictable lifecycle that scales from a single prompt to incident-driven remediation."
          />

          <div className="mt-10">
            <div className="grid gap-4 md:grid-cols-5">
              {happyPath.map((step, idx) => {
                const Icon = step.icon;
                return (
                  <Card key={step.title} className="rounded-2xl border bg-muted/35">
                    <CardContent className="p-5">
                      <div className="flex items-center justify-between">
                        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary ring-1 ring-primary/10">
                          <Icon className="h-5 w-5" />
                        </div>
                        <Badge variant="secondary" className="rounded-full text-[10px]">
                          Step {idx + 1}
                        </Badge>
                      </div>
                      <p className="mt-4 text-sm font-semibold tracking-tight">{step.title}</p>
                      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{step.description}</p>
                    </CardContent>
                  </Card>
                );
              })}
            </div>

            <div className="mt-4 hidden md:block">
              <div className="h-px w-full bg-gradient-to-r from-transparent via-border to-transparent" />
            </div>
          </div>
        </section>

        {/* audiences */}
        <section className="space-y-8">
          <SectionHeader
            eyebrow="Built for every layer"
            title="Teams that ship faster with safer automation."
            subtitle="From incident response to AI engineers—same isolation, same auditability."
          />
          <div className="grid gap-4 md:grid-cols-4">
            {audiences.map((item) => {
              const Icon = item.icon;
              return (
                <Card className="group h-full rounded-2xl border bg-background/70 shadow-sm backdrop-blur transition hover:-translate-y-0.5 hover:shadow-lg" key={item.title}>
                  <CardContent className="space-y-3 p-5">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary ring-1 ring-primary/10">
                      <Icon className="h-5 w-5" />
                    </div>
                    <p className="text-sm font-semibold tracking-tight">{item.title}</p>
                    <p className="text-xs leading-relaxed text-muted-foreground">{item.description}</p>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </section>

        {/* stack */}
        <section id="stack" className="overflow-hidden rounded-3xl border bg-slate-950 text-slate-50 shadow-2xl">
          <div className="px-6 pt-8 sm:px-8">
            <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-300">Platform stack</p>
            <h3 className="mt-2 text-2xl font-semibold tracking-tight">Opinionated, secure, production-ready.</h3>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-300">
              Django/Celery core, streaming-first UI, and hardened sandboxing primitives—deployable on Docker Compose or Kubernetes.
            </p>
          </div>

          <div className="mt-6 grid md:grid-cols-3">
            {stackColumns.map((col) => (
              <div key={col.title} className="p-6 sm:p-8">
                <p className="text-sm font-semibold uppercase tracking-[0.25em] text-slate-300">{col.title}</p>
                <Separator className="my-4 bg-white/10" />
                <ul className="space-y-2 text-sm">
                  {col.items.map((item) => (
                    <li key={item} className="flex items-start gap-2 text-slate-100/90">
                      <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                      <span className="leading-relaxed">{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="border-t border-white/10 bg-black/30 px-6 py-8 text-center sm:px-10">
            <h3 className="text-xl font-semibold">Ready to ship agents safely?</h3>
            <p className="mt-2 text-sm text-slate-300">
              Run locally with Docker Compose or deploy to Kubernetes—same sandbox guarantees.
            </p>
            <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
              <Button asChild className="rounded-full px-5">
                <Link to={primaryCta}>{isAuthenticated ? "Open console" : "Start free trial"}</Link>
              </Button>
              <Button asChild variant="outline" className="rounded-full border-white/15 bg-white/5 px-5 text-slate-50 hover:bg-white/10">
                <a href="https://pypi.org/project/astraforge-toolkit/">pip install astraforge-toolkit</a>
              </Button>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
