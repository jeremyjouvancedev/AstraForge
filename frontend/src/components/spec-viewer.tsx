export interface SpecViewerProps {
  spec?: string;
}

export function SpecViewer({ spec }: SpecViewerProps) {
  return (
    <div className="space-y-2">
      {spec ? <div dangerouslySetInnerHTML={{ __html: spec }} /> : <p>No spec generated yet.</p>}
    </div>
  );
}
