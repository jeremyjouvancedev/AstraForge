import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/cn";
import type { RunLogEvent } from "@/features/requests/hooks/use-run-log-stream";

interface RunLogViewerProps {
  events: RunLogEvent[];
  className?: string;
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
};

function formatLabel(event: RunLogEvent) {
  if (event.stage && stageLabels[event.stage]) {
    return stageLabels[event.stage];
  }
  if (event.type === "command") {
    return "Command";
  }
  if (event.type === "error") {
    return "Error";
  }
  return "Event";
}

export function RunLogViewer({ events, className }: RunLogViewerProps) {
  return (
    <Card className={cn("border-dashed", className)}>
      <CardHeader>
        <CardTitle className="text-sm font-semibold">Run activity</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm text-muted-foreground">
        {events.length === 0 ? (
          <p>No events yet. Start the implementation to stream progress.</p>
        ) : (
          <ul className="space-y-2">
            {events.map((event, index) => (
              <li
                key={`${event.type ?? "event"}-${index}`}
                className="rounded border border-border/60 bg-background/40 p-3"
              >
                <div className="flex items-center justify-between text-xs uppercase tracking-wide text-foreground">
                  <span className="font-semibold">{formatLabel(event)}</span>
                  {event.stage && <span>{event.stage}</span>}
                </div>
                {event.message && <p className="mt-1 whitespace-pre-wrap text-sm">{event.message}</p>}
                {event.type === "command" && event.command && (
                  <pre className="mt-2 overflow-x-auto rounded bg-muted p-2 text-xs text-foreground/80">
                    <code>{event.command}</code>
                  </pre>
                )}
                {event.output && (
                  <pre className="mt-2 overflow-x-auto rounded bg-muted p-2 text-xs text-foreground/80">
                    <code>{event.output}</code>
                  </pre>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
