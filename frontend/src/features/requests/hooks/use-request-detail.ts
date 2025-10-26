import { useQuery } from "@tanstack/react-query";

import { fetchRequestDetail } from "@/lib/api-client";

const TERMINAL_STATES = new Set([
  "PATCH_READY",
  "FAILED",
  "MR_OPENED",
  "REVIEWED",
  "DONE",
]);

export function useRequestDetail(requestId: string) {
  return useQuery({
    queryKey: ["request-detail", requestId],
    enabled: Boolean(requestId),
    queryFn: () => fetchRequestDetail(requestId),
    refetchInterval: (data) => {
      if (!requestId) {
        return false;
      }
      if (!data || !TERMINAL_STATES.has(data.state)) {
        return 3000;
      }
      return false;
    },
  });
}
