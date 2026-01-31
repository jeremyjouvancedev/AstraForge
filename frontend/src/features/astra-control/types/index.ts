import { type AstraControlSession } from "@/lib/api-client";

export type { AstraControlSession };

export interface PlanStep {
  title: string;
  description: string;
  status: 'todo' | 'in_progress' | 'completed';
}

export interface AgentMessage {
  role: 'assistant' | 'user' | 'tool';
  content: string;
  tool_calls?: Array<{
    name: string;
    args: Record<string, unknown>;
  }>;
}

export interface AgentPayload {
  messages?: AgentMessage[];
  plan_steps?: PlanStep[];
  plan?: string;
  is_finished?: boolean;
  summary?: string;
  file_tree?: string[];
}

export interface InterruptPayload {
  action: string;
  description?: string;
  timestamp: number;
  content_preview?: string;
  reason?: string;
  question?: string;
  choices?: string[];
  command?: string;
  cwd?: string;
  [key: string]: unknown;
}

export interface HumanInputPayload {
  message?: string;
  human_input?: {
    message: string;
    timestamp: number;
  };
}

export interface DocumentMetadata {
  filename: string;
  sandbox_path: string;
  description?: string;
  size_bytes: number;
  content_type: string;
  uploaded_at: number;
}

export interface DocumentUploadedPayload {
  filename: string;
  path: string;
  description?: string;
  timestamp: number;
}

export interface AgentEvent {
  type: string;
  payload: AgentPayload | InterruptPayload | HumanInputPayload | DocumentUploadedPayload;
  timestamp: number;
}
