import { Button } from "@/components/ui/button";

interface ChatApprovalBarProps {
  onApprove: () => void;
  onRequestChanges: () => void;
  status?: "pending" | "approved" | "changes";
}

export function ChatApprovalBar({ onApprove, onRequestChanges, status = "pending" }: ChatApprovalBarProps) {
  return (
    <div className="flex items-center justify-between rounded-md border bg-card p-4">
      <div>
        <h3 className="text-sm font-semibold">Chat Review Status</h3>
        <p className="text-xs text-muted-foreground">Current decision: {status}</p>
      </div>
      <div className="flex gap-2">
        <Button variant="outline" onClick={onRequestChanges}>
          Request Changes
        </Button>
        <Button onClick={onApprove}>Approve</Button>
      </div>
    </div>
  );
}
