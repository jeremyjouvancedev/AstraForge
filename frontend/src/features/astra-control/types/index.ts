import { type AstraControlSession } from "@/lib/api-client";

export type { AstraControlSession };

export interface PlanStep {
  title: string;
  description: string;
  status: 'todo' | 'in_progress' | 'completed';
}

export interface AgentEvent {
  type: string;
  payload: Record<string, unknown> & { plan_steps?: PlanStep[]; plan?: string };
  timestamp: number;
}
