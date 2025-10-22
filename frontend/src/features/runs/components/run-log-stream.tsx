import { useEffect, useState } from "react";

interface RunLogStreamProps {
  runId: string;
}

export function RunLogStream({ runId }: RunLogStreamProps) {
  const [logs, setLogs] = useState<string[]>([]);

  useEffect(() => {
    const source = new EventSource(`/api/runs/${runId}/logs/stream`);

    source.onmessage = (event) => {
      setLogs((previous) => [...previous, event.data]);
    };

    source.onerror = () => {
      source.close();
    };

    return () => {
      source.close();
    };
  }, [runId]);

  return (
    <div className="h-64 overflow-y-auto rounded border bg-card p-4 font-mono text-sm">
      {logs.length === 0 ? <p className="text-muted-foreground">Waiting for logs…</p> : logs.map((line, index) => <div key={index}>{line}</div>)}
    </div>
  );
}
