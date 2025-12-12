# AstraForge — Agent Sandbox One Pager

## What it solves
- **Safe agent execution at scale**: Run DeepAgent, Codex, or any coding CLI inside hardened Docker/K8s sandboxes with read-only roots, dropped caps, and controlled egress.
- **Translate specs to code automatically**: Feed a natural-language spec to an agent; it writes, tests, and prepares a merge-ready patch inside the sandbox.
- **Background remediation from alerts** (incoming): Wire error streams (Sentry/Glitchtip planned) to trigger Codex workspaces that reproduce, patch, and propose an MR without manual triage.
- **Visibility and trust**: Every command, diff, artifact, and chat event is streamed and persisted, so reviewers and auditors see exactly what ran.
- **Long-running LLM work**: Complex agent tasks can exceed context windows; AstraForge offloads intermediate state and artifacts to secure sandboxes instead of stuffing everything into the prompt.

## What AstraForge is
A **sandbox platform for AI and coding agents** with two clear tracks:
- **Coding sandboxes**: Codex CLI and other coding CLIs run in isolated workspaces to translate specs into code, patch bugs, and prep merge requests.
- **DeepAgent backend sandboxes**: Hosted LangChain DeepAgent runtime with the same sandbox guarantees for conversational/agentic flows.

## Who it’s for
- **SRE/Incident Response**: Auto-reproduce errors (Sentry/Glitchtip webhook support incoming) in a sandbox, validate the fix, and ship the MR with full run history.
- **Platform/Infra**: Safely run agents that evolve Terraform, Helm, or CI with repo/path allowlists and audit trails.
- **Product Engineering**: Capture intent as a prompt, let the agent code in a sandbox, then review diffs/tests before merge.
- **AI/Agent Engineers**: Run DeepAgent or custom AI agents at scale with consistent isolation, egress controls, and replayable runs.

## Core capabilities
- **Coding sandboxes**: Docker/K8s workspaces for Codex and other CLIs that turn specs into code, run tests, and prep merge-ready branches.
- **DeepAgent backend sandboxes**: Managed LangChain DeepAgent runtime with sandboxed execution and the same isolation controls.
- **Secure-by-default runtime**: Read-only roots, tmpfs workdirs, seccomp, dropped capabilities, curated egress, idle/TTL reaping, and snapshots.
- **Run transparency**: SSE-streamed logs, diffs, chat, and artifacts; every action is replayable.
- **Autonomous remediation hooks** (incoming): Wire alerting sources (Sentry/Glitchtip planned) to auto-create a sandbox run that patches and proposes an MR when errors hit production.
- **Consistent contract**: Same sandbox/run model across UI, REST API, and the `astraforge-toolkit` Python package.
- **Shared blackboard**: Use a sandbox as a shared workspace where multiple LangChain DeepAgent agents (and supporting tools/CLIs) exchange files, diffs, and artifacts safely.
- **Repo/path guardrails**: Repository and path allowlists keep agent writes constrained to approved codebases, with full audit history.
- **Context offloading**: Agents persist checkpoints, files, and logs to the sandbox filesystem so long tasks stay performant without overloading the LLM context.

## How it works (happy path)
1) **Capture a prompt or alert** via the UI/API (`/requests/`) or incoming Sentry/Glitchtip webhook.  
2) **Or call via SDK**: `pip install astraforge-toolkit` and use `DeepAgentClient`/`SandboxBackend` to open/reuse sandboxes programmatically (same contract as UI/API).  
3) **Pick your track**: provision a sandbox for Codex/CLI (coding sandbox) or for DeepAgent (backend sandbox) on Docker or Kubernetes.  
4) **Run the agent**: it reads the spec, edits code, runs tests, and prepares a branch/patch.  
5) **Stream everything** over SSE: commands, diffs, artifacts, chat, and test results.  
6) **Review & merge**: approve the MR-quality output or rerun with more guidance; history stays audit-ready.

## Stack at a glance
- **Backend**: Django + DRF, Celery workers, Redis Streams, Postgres (+pgvector), S3/MinIO artifacts.
- **Frontend**: Vite + React Query + shadcn/ui SPA streaming live runs/diffs.
- **Sandboxing**: Docker or Kubernetes provisioners with seccomp/read-only roots, idle/TTL reaping, snapshots.
- **Coding sandboxes**: Codex CLI and other coding toolchains run inside provisioned sandboxes with full run logging.
- **DeepAgent backend**: Managed LangChain DeepAgent runtime wired to the same sandbox controls and streaming model.
- **SDK/CLI**: `astraforge-toolkit` (Python) mirrors the sandbox contract; Codex CLI support for workspace automation.

## Why teams pick it
- **Sandbox-first**: Purpose-built to run agents safely—at one or hundreds of concurrent sandboxes—with consistent isolation.
- **Speed with control**: Agents work fast; humans keep final say with full run visibility and policy enforcement.
- **Unified model**: Same contract across browser, API, SDK, and incident webhooks.
- **Hybrid-ready**: Compose for local dev, Kubernetes overlays for clusters; identical env vars and behavior.

## Getting started
- Local: `make install-deps` → configure `.env` → `pnpm dev` (frontend) and `make backend-serve` (backend).
- Containers: `docker compose up` (see `docs/docker-compose.md`), or use `infra/k8s/local` for k8s.
- SDK: `pip install astraforge-toolkit` and call `DeepAgentClient`/`SandboxBackend` against your API URL.

## Quick pitch
**AstraForge is the sandbox platform for AI and coding agents—turning specs or production alerts into safe, observable, merge-ready code.**
