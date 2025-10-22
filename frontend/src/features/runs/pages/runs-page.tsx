import { useState } from "react";

import { RunLogStream } from "@/features/runs/components/run-log-stream";

const sampleRuns = [
  { id: "123e4567", stage: "PLAN", status: "running" },
  { id: "223e4567", stage: "EXECUTION", status: "success" }
];

export default function RunsPage() {
  const [selectedRun, setSelectedRun] = useState<string | null>(sampleRuns[0]?.id ?? null);

  return (
    <div className="mx-auto flex max-w-5xl gap-6 p-6">
      <aside className="w-64 space-y-2">
        <h2 className="text-sm font-semibold text-muted-foreground">Recent Runs</h2>
        <ul className="space-y-1">
          {sampleRuns.map((run) => (
            <li key={run.id}>
              <button
                type="button"
                onClick={() => setSelectedRun(run.id)}
                className={`w-full rounded border px-3 py-2 text-left text-sm ${
                  selectedRun === run.id ? "border-primary text-primary" : "text-muted-foreground"
                }`}
              >
                <div className="font-semibold">Run {run.id.slice(0, 4)}</div>
                <div className="text-xs">{run.stage} • {run.status}</div>
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <section className="flex-1 space-y-4">
        <header>
          <h1 className="text-xl font-semibold">Workspace Logs</h1>
          <p className="text-sm text-muted-foreground">Live stream of execution output.</p>
        </header>
        {selectedRun ? <RunLogStream runId={selectedRun} /> : <p>Select a run to view logs.</p>}
      </section>
    </div>
  );
}
