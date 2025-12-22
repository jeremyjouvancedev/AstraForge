import { useQuery } from "@tanstack/react-query";

import { fetchRepositoryLinks } from "@/lib/api-client";

export function useRepositoryLinks(workspaceUid?: string) {
  return useQuery({
    queryKey: ["repository-links", workspaceUid || "none"],
    queryFn: () => fetchRepositoryLinks(workspaceUid),
    enabled: Boolean(workspaceUid)
  });
}
