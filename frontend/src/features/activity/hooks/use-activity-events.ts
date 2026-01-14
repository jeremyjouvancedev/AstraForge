import { useInfiniteQuery } from "@tanstack/react-query";

import { fetchActivityEvents } from "@/lib/api-client";

const DEFAULT_PAGE_SIZE = 25;

export const activityEventsQueryKey = (tenantId?: string) =>
  ["activity-events", tenantId ?? "all"] as const;

export function useActivityEvents(tenantId?: string, pageSize = DEFAULT_PAGE_SIZE) {
  return useInfiniteQuery({
    queryKey: activityEventsQueryKey(tenantId),
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      fetchActivityEvents({
        tenantId,
        page:
          typeof pageParam === "number" && !Number.isNaN(pageParam)
            ? pageParam
            : 1,
        pageSize
      }),
    getNextPageParam: (lastPage) => lastPage.next_page ?? undefined
  });
}
