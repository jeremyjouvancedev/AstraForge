interface DiffPreviewProps {
  diff?: string;
}

export function DiffPreview({ diff }: DiffPreviewProps) {
  return (
    <pre className="whitespace-pre-wrap rounded border bg-card p-4 font-mono text-xs">
      {diff ?? "Diff preview not available yet."}
    </pre>
  );
}
