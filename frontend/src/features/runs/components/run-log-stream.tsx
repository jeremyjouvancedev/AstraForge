import { useEffect, useRef, useState } from "react";

interface RunLogStreamProps {
  runId: string;
}

export function RunLogStream({ runId }: RunLogStreamProps) {
  const [logs, setLogs] = useState<string[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    // Keep the viewport pinned to the latest log entry.
    requestAnimationFrame(() => {
      container.scrollTop = container.scrollHeight;
    });
  }, [logs]);

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950 shadow-lg">
      <div className="flex items-center gap-2 border-b border-zinc-800 px-3 py-2">
        <span className="h-2.5 w-2.5 rounded-full bg-red-500" aria-hidden />
        <span className="h-2.5 w-2.5 rounded-full bg-yellow-500" aria-hidden />
        <span className="h-2.5 w-2.5 rounded-full bg-green-500" aria-hidden />
        <span className="ml-2 text-xs uppercase tracking-wide text-zinc-400">Terminal</span>
      </div>
      <div
        ref={containerRef}
        className="h-64 overflow-y-auto bg-zinc-950 px-4 py-3 font-mono text-sm text-emerald-100"
      >
        {logs.length === 0 ? (
          <p className="text-emerald-500/70">Waiting for logs…</p>
        ) : (
          logs.map((line, index) => (
            <div key={index} className="whitespace-pre-wrap break-words">
              {line}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
