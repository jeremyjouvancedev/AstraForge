import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  acknowledgeComputerUseRun,
  createComputerUseRun,
  fetchComputerUseRun,
  fetchComputerUseRuns,
  fetchComputerUseTimeline,
  type ComputerUseTimelineItem,
  type ComputerUseRun,
  type CreateComputerUseRunInput
} from "@/lib/api-client";

export const computerUseRunsQueryKey = ["computer-use-runs"] as const;

type QueryLike<T> = { state?: { data?: T } };

function resolveQueryData<T>(value: unknown): T | undefined {
  if (value && typeof value === "object" && "state" in value) {
    return (value as QueryLike<T>).state?.data;
  }
  return value as T | undefined;
}

function resolveRunList(value: unknown): ComputerUseRun[] | null {
  const data = resolveQueryData<ComputerUseRun[] | undefined>(value);
  return Array.isArray(data) ? data : null;
}

export function useComputerUseRuns() {
  return useQuery<ComputerUseRun[]>({
    queryKey: computerUseRunsQueryKey,
    queryFn: fetchComputerUseRuns,
    refetchInterval: (value) => {
      const data = resolveRunList(value);
      if (!data) return false;
      if (data.some((run) => ["running", "awaiting_ack"].includes(run.status))) {
        return 5000;
      }
      return false;
    }
  });
}

export const computerUseRunQueryKey = (id: string) => ["computer-use-run", id] as const;

export function useComputerUseRun(id: string | null) {
  return useQuery<ComputerUseRun>({
    queryKey: id ? computerUseRunQueryKey(id) : ["computer-use-run", "placeholder"],
    queryFn: () => fetchComputerUseRun(id as string),
    enabled: Boolean(id),
    refetchInterval: (value) => {
      const data = resolveQueryData<ComputerUseRun | undefined>(value);
      if (!data) return false;
      if (["running", "awaiting_ack"].includes(data.status)) {
        return 3000;
      }
      return false;
    }
  });
}

export const computerUseTimelineQueryKey = (
  id: string,
  options?: { limit?: number; includeScreenshots?: boolean }
) =>
  [
    "computer-use-timeline",
    id,
    options?.limit ?? null,
    Boolean(options?.includeScreenshots)
  ] as const;

export function useComputerUseTimeline(
  id: string | null,
  options?: { limit?: number; includeScreenshots?: boolean; runStatus?: string | null }
) {
  return useQuery<ComputerUseTimelineItem[]>({
    queryKey: id
      ? computerUseTimelineQueryKey(id, options)
      : ["computer-use-timeline", "placeholder"],
    queryFn: () => fetchComputerUseTimeline(id as string, options),
    enabled: Boolean(id),
    refetchInterval: options?.runStatus
      ? ["running", "awaiting_ack"].includes(options.runStatus)
        ? 4000
        : false
      : false
  });
}

export function useCreateComputerUseRun() {
  const queryClient = useQueryClient();
  return useMutation<ComputerUseRun, Error, CreateComputerUseRunInput>({
    mutationFn: createComputerUseRun,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: computerUseRunsQueryKey });
      if (data?.id) {
        queryClient.invalidateQueries({ queryKey: computerUseRunQueryKey(data.id) });
      }
    }
  });
}

export function useAcknowledgeComputerUseRun() {
  const queryClient = useQueryClient();
  return useMutation<ComputerUseRun, Error, { id: string; decision: "approve" | "deny"; acknowledged: string[] }>({
    mutationFn: acknowledgeComputerUseRun,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: computerUseRunsQueryKey });
      if (data?.id) {
        queryClient.invalidateQueries({ queryKey: computerUseRunQueryKey(data.id) });
      }
    }
  });
}
