import { useQuery } from "@tanstack/react-query";

import {
  fetchMergeRequestDetail,
  fetchMergeRequests,
  type MergeRequestItem
} from "@/lib/api-client";

export const mergeRequestsQueryKey = ["merge-requests"] as const;

export function useMergeRequests() {
  return useQuery<MergeRequestItem[]>({
    queryKey: mergeRequestsQueryKey,
    queryFn: fetchMergeRequests
  });
}

export const mergeRequestDetailQueryKey = (id: string) =>
  ["merge-request", id] as const;

export function useMergeRequestDetail(id: string | null, options?: { enabled?: boolean }) {
  return useQuery<MergeRequestItem>({
    queryKey: id ? mergeRequestDetailQueryKey(id) : ["merge-request", "placeholder"],
    queryFn: () => fetchMergeRequestDetail(id as string),
    enabled: Boolean(id) && (options?.enabled ?? true)
  });
}
