import { Link } from "react-router-dom";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

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
    return <Card className="p-6">No requests yet. Submit one to get started.</Card>;
  }

  return (
    <ul className="space-y-3">
      {data.map((request) => (
        <li key={request.id}>
          {onSelect ? (
            <button
              type="button"
              onClick={() => onSelect(request)}
              className="w-full rounded border p-4 text-left transition-colors hover:bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-semibold">{request.payload.title}</h3>
                  <p className="text-sm text-muted-foreground">
                    {request.payload.description}
                  </p>
                </div>
                <span className="rounded bg-secondary px-3 py-1 text-xs uppercase">{request.state}</span>
              </div>
            </button>
          ) : (
            <Link
              to={`/requests/${request.id}/run`}
              className="block rounded border p-4 transition-colors hover:bg-muted"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-semibold">{request.payload.title}</h3>
                  <p className="text-sm text-muted-foreground">
                    {request.payload.description}
                  </p>
                </div>
                <span className="rounded bg-secondary px-3 py-1 text-xs uppercase">{request.state}</span>
              </div>
            </Link>
          )}
        </li>
      ))}
    </ul>
  );
}
