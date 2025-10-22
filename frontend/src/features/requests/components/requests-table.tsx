import { NavLink } from "react-router-dom";

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
}

export function RequestsTable({ data, isLoading }: RequestsTableProps) {
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
          <NavLink to={`/requests/${request.id}`} className="block rounded border p-4 hover:bg-muted">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold">{request.payload.title}</h3>
                <p className="text-sm text-muted-foreground">
                  {request.payload.description}
                </p>
              </div>
              <span className="rounded bg-secondary px-3 py-1 text-xs uppercase">{request.state}</span>
            </div>
          </NavLink>
        </li>
      ))}
    </ul>
  );
}
