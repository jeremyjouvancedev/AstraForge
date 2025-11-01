import { useEffect, useMemo, useRef } from "react";
import { cn } from "@/lib/cn";
import type { RunLogEvent } from "@/lib/api-client";

interface RunLogViewerProps {
  events: RunLogEvent[];
  className?: string;
  fillHeight?: boolean;
}

const stageLabels: Record<string, string> = {
  spec: "Specification",
  workspace: "Workspace",
  proxy: "Proxy",
  clone: "Repository Clone",
  spec_upload: "Spec Upload",
  codex: "Codex Execution",
  diff: "Diff Collection",
  execution: "Execution",
  mr: "Merge Request",
  provisioning: "Provisioning",
  git: "Git",
};

function formatStage(stage?: string | null) {
  if (!stage) return null;
  return stageLabels[stage] ?? stage;
}

function classify(line: string): "command" | "path" | "error" | "ok" | "neutral" {
  if (line.startsWith("$")) return "command";
  if (line.startsWith("✖")) return "error";
  if (line.startsWith("✔") || line.startsWith("…")) return "ok";
  if (line.startsWith("/") || line.startsWith("./") || line.startsWith("../")) return "path";
  if (/\.py\b|\.ts\b|\.tsx\b|\.js\b/.test(line)) return "path";
  if (line.startsWith("›")) return "neutral";
  return "neutral";
}

function formatEvent(event: RunLogEvent): Array<{ line: string; tone: ReturnType<typeof classify> }> {
  const entries: Array<{ line: string; tone: ReturnType<typeof classify> }> = [];
  const stageLabel = formatStage(event.stage);
  const prefix = stageLabel ? `[${stageLabel}] ` : "";

  switch (event.type) {
    case "heartbeat":
      entries.push({ line: "… Connected to run log stream", tone: "ok" });
      break;
    case "status":
      entries.push({ line: `${prefix}${event.message ?? "Status update"}`, tone: "neutral" });
      break;
    case "command":
      if (event.command) {
        entries.push({ line: `$ ${event.command}`, tone: "command" });
      }
      if (event.message) {
        entries.push({ line: `› ${event.message}`, tone: "neutral" });
      }
      if (event.output) {
        entries.push({ line: event.output, tone: classify(event.output) });
      }
      break;
    case "log":
      if (event.message) {
        entries.push({ line: event.message, tone: classify(event.message) });
      }
      break;
    case "error":
      entries.push({ line: `✖ ${prefix}${event.message ?? "An error occurred"}`, tone: "error" });
      if (event.output) {
        entries.push({ line: event.output, tone: "error" });
      }
      break;
    case "completed":
      entries.push({ line: "✔ Execution finished", tone: "ok" });
      break;
    default: {
      if (event.message) {
        entries.push({ line: `${prefix}${event.message}`, tone: "neutral" });
      } else if (stageLabel) {
        entries.push({ line: `${stageLabel}`, tone: "neutral" });
      }
      if (event.output) {
        entries.push({ line: event.output, tone: classify(event.output) });
      }
    }
  }

  return entries.filter((entry) => Boolean(entry.line?.trim()));
}

export function RunLogViewer({ events, className, fillHeight = false }: RunLogViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const lines = useMemo(() => events.flatMap(formatEvent), [events]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    container.scrollTop = container.scrollHeight;
  }, [lines]);

  return (
    <div
      className={cn(
        "flex flex-col overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg",
        className
      )}
    >
      <div className="flex items-center gap-2 border-b border-zinc-800 bg-zinc-900/80 px-4 py-2">
        <span className="h-2.5 w-2.5 rounded-full bg-red-500" aria-hidden />
        <span className="h-2.5 w-2.5 rounded-full bg-yellow-500" aria-hidden />
        <span className="h-2.5 w-2.5 rounded-full bg-green-500" aria-hidden />
        <span className="ml-2 text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400">Run Log</span>
      </div>
      <div
        ref={containerRef}
        className={cn(
          "flex-1 overflow-y-auto bg-zinc-950 px-4 py-3 font-mono text-sm leading-relaxed tracking-tight text-emerald-100",
          fillHeight ? "min-h-[18rem] max-h-[70vh]" : "max-h-72"
        )}
      >
        {lines.length === 0 ? (
          <p className="text-emerald-500/70">Connecting to Codex run stream…</p>
        ) : (
          lines.map(({ line, tone }, index) => (
            <div
              key={`${line}-${index}`}
              className={cn(
                "whitespace-pre-wrap break-words",
                tone === "command" && "text-sky-300",
                tone === "error" && "text-red-300",
                tone === "ok" && "text-emerald-300",
                tone === "path" && "text-amber-200",
                tone === "neutral" && "text-emerald-100"
              )}
            >
              {line}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
