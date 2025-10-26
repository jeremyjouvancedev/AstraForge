import { useQuery } from "@tanstack/react-query";

import { fetchRequests } from "@/lib/api-client";

export function useRequests() {
  return useQuery({
    queryKey: ["requests"],
    queryFn: fetchRequests
  });
}
