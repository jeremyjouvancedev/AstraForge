import { useQuery } from "@tanstack/react-query";

import { fetchSandboxSessions, type SandboxSession } from "@/lib/api-client";

export const sandboxSessionsQueryKey = ["sandbox-sessions"] as const;

export function useSandboxSessions() {
  return useQuery<SandboxSession[]>({
    queryKey: sandboxSessionsQueryKey,
    queryFn: fetchSandboxSessions
  });
}
