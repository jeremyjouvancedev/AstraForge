import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface RequestRow {
  id: string;
  payload: {
    title: string;
    description: string;
  };
  state: string;
}

interface RequestsTableProps {
  isLoading: boolean;
  data?: RequestRow[];
  onSelect?: (request: RequestRow) => void;
}

function statusTone(status: string) {
  const value = status.toLowerCase();
  if (value.includes("error") || value.includes("failed")) {
    return "bg-destructive/15 text-destructive";
  }
  if (value.includes("completed") || value.includes("done") || value.includes("success")) {
    return "bg-emerald-500/15 text-emerald-500";
  }
  if (value.includes("running") || value.includes("in_progress")) {
    return "bg-primary/15 text-primary";
  }
  return "bg-muted/70 text-muted-foreground";
}

export function RequestsTable({ data, isLoading, onSelect }: RequestsTableProps) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        {[...Array(5)].map((_, index) => (
          <Skeleton key={index} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border/70 bg-muted/30 p-6 text-center text-sm text-muted-foreground">
        No requests yet. Submit one to get started.
      </div>
    );
  }

  return (
    <ul className="space-y-3">
      {data.map((request) => (
        <li key={request.id}>
          {onSelect ? (
            <button
              type="button"
              onClick={() => onSelect(request)}
              className="group w-full rounded-2xl border border-border/60 bg-card/70 px-5 py-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-primary/50 hover:bg-card focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
            >
              <div className="flex items-center justify-between">
                <div className="min-w-0 space-y-1">
                  <p className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">
                    Request
                  </p>
                  <h3 className="truncate text-base font-semibold text-foreground group-hover:text-primary">
                    {request.payload.title}
                  </h3>
                  <p className="line-clamp-2 text-sm text-muted-foreground">
                    {request.payload.description}
                  </p>
                </div>
                <Badge className={cn("shrink-0 rounded-full px-3 py-1 text-[11px] capitalize", statusTone(request.state))}>
                  {request.state.replace(/_/g, " ")}
                </Badge>
              </div>
            </button>
          ) : (
            <Link
              to={`/app/requests/${request.id}/run`}
              className="group block rounded-2xl border border-border/60 bg-card/70 px-5 py-4 shadow-sm transition hover:-translate-y-0.5 hover:border-primary/50 hover:bg-card"
            >
              <div className="flex items-center justify-between">
                <div className="min-w-0 space-y-1">
                  <p className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">
                    Request
                  </p>
                  <h3 className="truncate text-base font-semibold text-foreground group-hover:text-primary">
                    {request.payload.title}
                  </h3>
                  <p className="line-clamp-2 text-sm text-muted-foreground">
                    {request.payload.description}
                  </p>
                </div>
                <Badge className={cn("shrink-0 rounded-full px-3 py-1 text-[11px] capitalize", statusTone(request.state))}>
                  {request.state.replace(/_/g, " ")}
                </Badge>
              </div>
            </Link>
          )}
        </li>
      ))}
    </ul>
  );
}
