import { useMutation, useQueryClient } from "@tanstack/react-query";

import { stopSandboxSession } from "@/lib/api-client";
import { sandboxSessionsQueryKey } from "./use-sandbox-sessions";

export function useStopSandboxSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => stopSandboxSession(sessionId),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: sandboxSessionsQueryKey });
      queryClient.invalidateQueries({ queryKey: ["workspace-usage"] });
    }
  });
}
