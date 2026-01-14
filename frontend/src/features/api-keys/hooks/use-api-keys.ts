import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createApiKey, fetchApiKeys, revokeApiKey } from "@/lib/api-client";

export function useApiKeys() {
  return useQuery({
    queryKey: ["api-keys"],
    queryFn: fetchApiKeys
  });
}

export function useCreateApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => createApiKey(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    }
  });
}

export function useRevokeApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => revokeApiKey(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    }
  });
}
