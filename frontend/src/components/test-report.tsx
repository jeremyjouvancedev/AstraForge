export interface TestReportProps {
  results?: Array<{ name: string; status: "pass" | "fail" }>;
}

export function TestReport({ results = [] }: TestReportProps) {
  if (results.length === 0) {
    return <p className="text-sm text-muted-foreground">No test results yet.</p>;
  }

  return (
    <ul className="space-y-1 text-sm">
      {results.map((result) => (
        <li key={result.name} className="flex items-center justify-between rounded border px-3 py-2">
          <span>{result.name}</span>
          <span className={result.status === "pass" ? "text-green-500" : "text-destructive"}>
            {result.status.toUpperCase()}
          </span>
        </li>
      ))}
    </ul>
  );
}
