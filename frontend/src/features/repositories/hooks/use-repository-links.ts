import { useQuery } from "@tanstack/react-query";

import { fetchRepositoryLinks } from "@/lib/api-client";

export function useRepositoryLinks() {
  return useQuery({
    queryKey: ["repository-links"],
    queryFn: fetchRepositoryLinks
  });
}
