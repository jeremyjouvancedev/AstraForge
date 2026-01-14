import { useQuery } from "@tanstack/react-query";

import { fetchWorkspaceUsage, type WorkspaceUsageSummary } from "@/lib/api-client";

export function useWorkspaceUsage(workspaceUid?: string | null) {
  return useQuery<WorkspaceUsageSummary>({
    queryKey: ["workspace-usage", workspaceUid],
    queryFn: () => fetchWorkspaceUsage(workspaceUid as string),
    enabled: Boolean(workspaceUid),
    staleTime: 60 * 1000
  });
}
