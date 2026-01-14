import { useQuery } from "@tanstack/react-query";

import {
  fetchRunDetail,
  fetchRuns,
  type RunDetail,
  type RunSummary
} from "@/lib/api-client";

export const runsQueryKey = ["runs"] as const;

export function useRuns() {
  return useQuery<RunSummary[]>({
    queryKey: runsQueryKey,
    queryFn: fetchRuns
  });
}

export const runDetailQueryKey = (id: string) => ["run-detail", id] as const;

export function useRunDetail(id: string | null, options?: { enabled?: boolean }) {
  return useQuery<RunDetail>({
    queryKey: id ? runDetailQueryKey(id) : ["run-detail", "placeholder"],
    queryFn: () => fetchRunDetail(id as string),
    enabled: Boolean(id) && (options?.enabled ?? true)
  });
}
