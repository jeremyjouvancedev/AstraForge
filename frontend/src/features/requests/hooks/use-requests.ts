import { useQuery } from "@tanstack/react-query";

import { fetchRequests } from "@/lib/api-client";

export function useRequests(tenantId?: string) {
  const targetTenant = tenantId || "all";

  return useQuery({
    queryKey: ["requests", targetTenant],
    queryFn: async () => fetchRequests({ tenantId })
  });
}
