import axios from "axios";

export const apiClient = axios.create({
  baseURL: "/api",
  headers: {
    "Content-Type": "application/json"
  },
  withCredentials: true,
  xsrfCookieName: "csrftoken",
  xsrfHeaderName: "X-CSRFToken"
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("auth:unauthorized"));
      const path = window.location.pathname;
      if (path !== "/login" && path !== "/register") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export interface Attachment {
  uri: string;
  name: string;
  content_type: string;
}

export type ApiRequestPayload = {
  title: string;
  description: string;
  context?: Record<string, unknown>;
  attachments?: Array<Attachment>;
};

export interface RequestProject {
  id: string;
  provider: RepositoryProvider;
  repository: string;
  base_url?: string | null;
}

export interface CreateRequestResponse {
  id: string;
  state: string;
  tenant_id?: string;
  payload: ApiRequestPayload;
  project: RequestProject;
  created_at?: string;
  metadata?: Record<string, unknown>;
  artifacts?: Record<string, unknown>;
}

export interface CreateRequestInput {
  prompt: string;
  projectId: string;
  sender?: string;
  source?: string;
  tenantId?: string;
  llmProvider?: "openai" | "ollama" | "google";
  llmModel?: string;
  reasoningEffort?: "low" | "medium" | "high";
  reasoningCheck?: boolean;
  attachments?: Array<{ uri: string; name: string; content_type: string }>;
}

export async function createRequest(input: CreateRequestInput) {
  const trimmedModel = input.llmModel?.trim() ?? "";
  const response = await apiClient.post<CreateRequestResponse>("/requests/", {
    source: input.source ?? "direct_user",
    tenant_id: input.tenantId ?? "tenant-default",
    sender: input.sender ?? "user@example.com",
    project_id: input.projectId,
    prompt: input.prompt,
    ...(input.llmProvider ? { llm_provider: input.llmProvider } : {}),
    ...(trimmedModel ? { llm_model: trimmedModel } : {}),
    ...(input.reasoningEffort ? { reasoning_effort: input.reasoningEffort } : {}),
    ...(input.reasoningCheck !== undefined ? { reasoning_check: input.reasoningCheck } : {}),
    ...(input.attachments ? { attachments: input.attachments } : {})
  });
  return response.data;
}

export async function fetchRequests(filters?: { tenantId?: string }) {
  const response = await apiClient.get<CreateRequestResponse[]>("/requests/", {
    params: filters?.tenantId ? { tenant_id: filters.tenantId } : undefined
  });
  return response.data;
}

export async function fetchRequestDetail(id: string) {
  const response = await apiClient.get<CreateRequestResponse>(`/requests/${id}/`);
  return response.data;
}

export async function sendChatMessage(payload: {
  requestId: string;
  message: string;
  attachments?: Array<{ uri: string; name: string; content_type: string }>;
}) {
  const response = await apiClient.post<{ status: string }>("/chat/", {
    request_id: payload.requestId,
    message: payload.message,
    ...(payload.attachments ? { attachments: payload.attachments } : {})
  });
  return response.data;
}

export async function executeRequest(payload: {
  requestId: string;
}) {
  const response = await apiClient.post<{ status: string }>(
    `/requests/${payload.requestId}/execute/`,
    {}
  );
  return response.data;
}

export interface AuthUser {
  username: string;
  email: string;
  access: UserAccessInfo;
  auth?: AuthSettings;
  workspaces?: WorkspaceSummary[];
  default_workspace?: string | null;
}

export type AccessStatus = "pending" | "approved" | "blocked";

export interface UserAccessInfo {
  status: AccessStatus;
  identity_provider: string;
  approved_at?: string | null;
  updated_at: string;
  waitlist_enforced?: boolean;
  waitlist_notified_at?: string | null;
  waitlist_email_sent?: boolean;
}

export interface AuthSettings {
  require_approval: boolean;
  allow_all_users: boolean;
  waitlist_enabled: boolean;
  self_hosted: boolean;
  billing_enabled: boolean;
  supported_providers: string[];
}

export interface WorkspaceSummary {
  uid: string;
  name: string;
  role: string;
  plan?: string;
}

export type RepositoryWorkspace = Pick<WorkspaceSummary, "uid" | "name">;

export async function fetchWorkspaces() {
  const response = await apiClient.get<WorkspaceSummary[]>("/workspaces/");
  return response.data;
}

export async function createWorkspace(payload: { name: string }) {
  const response = await apiClient.post<WorkspaceSummary>("/workspaces/", payload);
  return response.data;
}

export async function ensureCsrfToken() {
  await apiClient.get("/auth/csrf/");
}

export async function registerUser(payload: { username: string; password: string; email?: string }) {
  await ensureCsrfToken();
  const response = await apiClient.post<AuthUser>("/auth/register/", payload);
  return response.data;
}

export async function loginUser(payload: { username: string; password: string }) {
  await ensureCsrfToken();
  const response = await apiClient.post<AuthUser>("/auth/login/", payload);
  return response.data;
}

export async function logoutUser() {
  await ensureCsrfToken();
  return apiClient.post("/auth/logout/");
}

export async function fetchCurrentUser() {
  const response = await apiClient.get<AuthUser>("/auth/me/");
  return response.data;
}

export async function fetchAuthSettings() {
  const response = await apiClient.get<AuthSettings>("/auth/settings/");
  return response.data;
}

export async function submitEarlyAccessRequest(payload: {
  email: string;
  teamRole?: string;
  projectSummary?: string;
}) {
  const response = await apiClient.post<{
    detail: string;
    user_email_sent: boolean;
    owner_email_sent: boolean;
  }>("/marketing/early-access/", {
    email: payload.email,
    team_role: payload.teamRole ?? "",
    project_summary: payload.projectSummary ?? ""
  });
  return response.data;
}

export type RepositoryProvider = "gitlab" | "github";

export interface RepositoryLink {
  id: string;
  provider: RepositoryProvider;
  repository: string;
  base_url?: string | null;
  workspace: RepositoryWorkspace;
  created_at: string;
  updated_at: string;
}

export interface CreateRepositoryLinkPayload {
  provider: RepositoryProvider;
  repository: string;
  access_token: string;
  base_url?: string;
  workspace_uid: string;
}

export async function fetchRepositoryLinks(workspaceUid?: string) {
  if (!workspaceUid) return [];
  const response = await apiClient.get<RepositoryLink[]>("/repository-links/", {
    params: { workspace_uid: workspaceUid }
  });
  return response.data;
}

export async function createRepositoryLink(payload: CreateRepositoryLinkPayload) {
  await ensureCsrfToken();
  const response = await apiClient.post<RepositoryLink>("/repository-links/", payload);
  return response.data;
}

export async function deleteRepositoryLink(id: string) {
  await ensureCsrfToken();
  await apiClient.delete(`/repository-links/${id}/`);
}

export interface RunLogEvent {
  request_id: string;
  run_id?: string;
  type?: string;
  stage?: string;
  message?: string;
  command?: string;
  cwd?: string | null;
  output?: string;
  exit_code?: number;
  [key: string]: unknown;
}

export interface RunSummary {
  id: string;
  request_id: string;
  request_title: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  diff_size: number;
}

export interface RunDetail extends RunSummary {
  events: RunLogEvent[];
  diff: string;
  reports?: Record<string, unknown>;
  artifacts?: Record<string, unknown>;
  error?: string;
}

// API keys ------------------------------------------------------------
export interface ApiKey {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
  is_active: boolean;
  key?: string; // present only at creation time
}

export async function fetchApiKeys() {
  const response = await apiClient.get<ApiKey[]>("/api-keys/");
  return response.data;
}

export async function createApiKey(name: string) {
  const response = await apiClient.post<ApiKey>("/api-keys/", { name });
  return response.data;
}

export async function revokeApiKey(id: string) {
  await apiClient.delete(`/api-keys/${id}/`);
}

export async function fetchRuns() {
  const response = await apiClient.get<RunSummary[]>("/runs/");
  return response.data;
}

export async function fetchRunDetail(id: string) {
  const response = await apiClient.get<RunDetail>(`/runs/${encodeURIComponent(id)}/`);
  return response.data;
}

export interface MergeRequestItem {
  id: string;
  request_id: string;
  request_title: string;
  title: string;
  description: string;
  target_branch?: string;
  source_branch?: string;
  status: string;
  ref: string;
  diff: string;
  created_at: string;
}

export async function fetchMergeRequests() {
  const response = await apiClient.get<MergeRequestItem[]>("/merge-requests/");
  return response.data;
}

export async function fetchMergeRequestDetail(id: string) {
  const response = await apiClient.get<MergeRequestItem>(
    `/merge-requests/${encodeURIComponent(id)}/`
  );
  return response.data;
}

export type ActivityEventType = "Request" | "Run" | "Merge" | "Sandbox";

export type ActivityConsumption =
  | {
      kind: "request";
      ordinal?: number | null;
    }
  | {
      kind: "sandbox";
      ordinal?: number | null;
      cpu_seconds?: number | null;
      storage_bytes?: number | null;
    };

export interface ActivityEventDto {
  id: string;
  type: ActivityEventType;
  title: string;
  description: string;
  timestamp: string;
  href?: string | null;
  consumption?: ActivityConsumption | null;
}

export interface ActivitySummary {
  total: number;
  requests: number;
  runs: number;
  merges: number;
  sandboxes: number;
}

export interface ActivityEventsPage {
  count: number;
  page: number;
  page_size: number;
  next_page: number | null;
  previous_page: number | null;
  results: ActivityEventDto[];
  summary: ActivitySummary;
}

export async function fetchActivityEvents(params: {
  tenantId?: string;
  page?: number;
  pageSize?: number;
}) {
  const queryParams: Record<string, string | number> = {
    page: params.page ?? 1,
    page_size: params.pageSize ?? 25
  };
  if (params.tenantId) {
    queryParams.tenant_id = params.tenantId;
  }
  const response = await apiClient.get<ActivityEventsPage>("/activity/", {
    params: queryParams
  });
  return response.data;
}

// Sandbox sessions ------------------------------------------------------------
export interface SandboxSession {
  id: string;
  mode: string;
  image?: string;
  status: string;
  created_at?: string;
  updated_at?: string;
  last_activity_at?: string | null;
  cpu_seconds?: number | null;
  storage_bytes?: number | null;
  metadata?: Record<string, unknown>;
}

export async function fetchSandboxSessions() {
  const response = await apiClient.get<SandboxSession[]>("/sandbox/sessions/");
  return response.data;
}

export async function stopSandboxSession(sessionId: string) {
  await apiClient.post(`/sandbox/sessions/${encodeURIComponent(sessionId)}/stop/`, {});
}

export interface SandboxUploadResult {
  exit_code: number;
  stdout: string;
  stderr: string;
}

export async function uploadSandboxFile(sessionId: string, path: string, content: Blob) {
  await ensureCsrfToken();
  const response = await apiClient.post<SandboxUploadResult>(
    `/sandbox/sessions/${encodeURIComponent(sessionId)}/files/upload/`,
    content,
    {
      headers: {
        "Content-Type": content.type || "application/octet-stream"
      },
      params: {
        path
      }
    }
  );
  return response.data;
}

export async function readSandboxFile(sessionId: string, path: string) {
  const response = await apiClient.get(
    `/sandbox/sessions/${encodeURIComponent(sessionId)}/files/content/`,
    {
      params: { path },
      responseType: 'text'
    }
  );
  return response.data as string;
}

// Computer-use runs -----------------------------------------------------------
export interface ComputerUseSafetyCheck {
  id: string;
  category: string;
  severity: "low" | "medium" | "high";
  message: string;
}

export interface ComputerUseRun {
  id: string;
  goal: string;
  status: string;
  stop_reason?: string;
  trace_dir?: string;
  sandbox_session_id?: string | null;
  pending_checks?: ComputerUseSafetyCheck[];
  final_response?: string | null;
  step_index?: number;
  created_at: string;
  updated_at: string;
}

export interface CreateComputerUseRunInput {
  goal: string;
  allowedDomains?: string[];
  blockedDomains?: string[];
  approvalMode?: "auto" | "on_risk" | "always";
  maxSteps?: number;
  maxRuntimeSeconds?: number;
  failureThreshold?: number;
  sandboxSessionId?: string;
  sandboxMode?: "docker" | "k8s";
  sandboxImage?: string;
  decisionProvider?: string;
  decisionScript?: Array<Record<string, unknown>>;
  llmProvider?: string;
  llmModel?: string;
  reasoningCheck?: boolean;
  reasoningEffort?: string;
}

export async function fetchComputerUseRuns() {
  const response = await apiClient.get<
    ComputerUseRun[] | { results?: ComputerUseRun[] | null }
  >("/computer-use/runs/");
  if (Array.isArray(response.data)) {
    return response.data;
  }
  const results = response.data?.results;
  if (Array.isArray(results)) {
    return results;
  }
  return [];
}

export async function fetchComputerUseRun(id: string) {
  const response = await apiClient.get<ComputerUseRun>(
    `/computer-use/runs/${encodeURIComponent(id)}/`
  );
  return response.data;
}

export async function createComputerUseRun(payload: CreateComputerUseRunInput) {
  const config: Record<string, unknown> = {};
  if (payload.allowedDomains?.length) {
    config.allowed_domains = payload.allowedDomains;
  }
  if (payload.blockedDomains?.length) {
    config.blocked_domains = payload.blockedDomains;
  }
  if (payload.approvalMode) {
    config.approval_mode = payload.approvalMode;
  }
  if (payload.maxSteps) {
    config.max_steps = payload.maxSteps;
  }
  if (payload.maxRuntimeSeconds) {
    config.max_runtime_seconds = payload.maxRuntimeSeconds;
  }
  if (payload.failureThreshold) {
    config.failure_threshold = payload.failureThreshold;
  }
  if (payload.llmProvider) {
    config.llm_provider = payload.llmProvider;
  }
  if (payload.llmModel) {
    config.llm_model = payload.llmModel;
  }
  if (payload.reasoningCheck !== undefined) {
    config.reasoning_check = payload.reasoningCheck;
  }
  if (payload.reasoningEffort) {
    config.reasoning_effort = payload.reasoningEffort;
  }

  const body: Record<string, unknown> = {
    goal: payload.goal,
    config
  };

  if (payload.decisionProvider) {
    body.decision_provider = payload.decisionProvider;
  }
  if (payload.decisionScript) {
    body.decision_script = payload.decisionScript;
  }

  if (payload.sandboxSessionId) {
    body.sandbox_session_id = payload.sandboxSessionId;
  } else {
    body.sandbox = {
      mode: payload.sandboxMode ?? "docker",
      ...(payload.sandboxImage ? { image: payload.sandboxImage } : {})
    };
  }

  const response = await apiClient.post<ComputerUseRun>("/computer-use/runs/", body);
  return response.data;
}

export async function acknowledgeComputerUseRun(payload: {
  id: string;
  decision: "approve" | "deny";
  acknowledged: string[];
}) {
  const response = await apiClient.post<ComputerUseRun>(
    `/computer-use/runs/${encodeURIComponent(payload.id)}/acknowledge/`,
    {
      decision: payload.decision,
      acknowledged: payload.acknowledged
    }
  );
  return response.data;
}

export type ComputerUseTimelineItem = {
  type: string;
  call_id?: string;
  debug_info?: Record<string, unknown>;
  action?: Record<string, unknown>;
  meta?: Record<string, unknown>;
  pending_safety_checks?: ComputerUseSafetyCheck[];
  output?: {
    url?: string;
    viewport?: { w: number; h: number };
    screenshot_b64?: string;
    execution?: {
      status?: string;
      error_type?: string;
      error_message?: string;
    };
  };
  decision?: string;
  reason?: string;
  checks?: ComputerUseSafetyCheck[];
  acknowledged?: string[];
};

export async function fetchComputerUseTimeline(
  id: string,
  options?: { limit?: number; includeScreenshots?: boolean }
) {
  const response = await apiClient.get<
    { items?: ComputerUseTimelineItem[] | null } | ComputerUseTimelineItem[]
  >(`/computer-use/runs/${encodeURIComponent(id)}/timeline/`, {
    params: {
      ...(options?.limit ? { limit: options.limit } : {}),
      ...(options?.includeScreenshots ? { include_screenshots: 1 } : {})
    }
  });
  if (Array.isArray(response.data)) {
    return response.data;
  }
  const items = response.data?.items;
  if (Array.isArray(items)) {
    return items;
  }
  return [];
}

// Workspace usage -------------------------------------------------------------
export interface WorkspacePlanLimits {
  requests_per_month?: number | null;
  sandbox_sessions_per_month?: number | null;
  sandbox_concurrent?: number | null;
}

export interface WorkspaceUsageStats {
  requests_per_month: number;
  sandbox_sessions_per_month: number;
  active_sandboxes: number;
  sandbox_seconds: number;
  artifacts_bytes: number;
}

export interface WorkspaceUsageSummary {
  plan: string;
  limits: WorkspacePlanLimits;
  usage: WorkspaceUsageStats;
  period_start: string;
  catalog: Record<string, WorkspacePlanLimits>;
}

export async function fetchWorkspaceUsage(workspaceUid: string) {
  const response = await apiClient.get<WorkspaceUsageSummary>(
    `/workspaces/${encodeURIComponent(workspaceUid)}/usage/`
  );
  return response.data;
}

export interface AstraControlSession {
  id: string;
  goal: string;
  status: "created" | "running" | "paused" | "completed" | "failed";
  sandbox_session?: string;
  created_at: string;
  updated_at: string;
}

export async function createAstraControlSession(payload: { 
  goal: string; 
  model?: string;
  provider?: string;
  reasoning_check?: boolean;
  reasoning_effort?: string;
  validation_required?: boolean;
}) {
  await ensureCsrfToken();
  const response = await apiClient.post<AstraControlSession>("/astra-control/sessions/", payload);
  return response.data;
}

export async function resumeAstraControlSession(id: string) {
  await ensureCsrfToken();
  const response = await apiClient.post<{ status: string }>(
    `/astra-control/sessions/${encodeURIComponent(id)}/resume/`,
    {}
  );
  return response.data;
}

export async function fetchAstraControlSession(id: string) {
  const response = await apiClient.get<AstraControlSession & { state: { events?: Record<string, unknown>[] } }>(
    `/astra-control/sessions/${encodeURIComponent(id)}/`
  );
  return response.data;
}

export async function fetchAstraControlSessions() {
  const response = await apiClient.get<AstraControlSession[]>("/astra-control/sessions/");
  return response.data;
}

export async function cancelAstraControlSession(id: string) {
  await ensureCsrfToken();
  const response = await apiClient.post<{ status: string }>(
    `/astra-control/sessions/${encodeURIComponent(id)}/cancel/`,
    {}
  );
  return response.data;
}

export async function sendAstraControlMessage(id: string, message: string, validation_required?: boolean) {
  await ensureCsrfToken();
  const response = await apiClient.post<{ status: string }>(
    `/astra-control/sessions/${encodeURIComponent(id)}/message/`,
    { message, validation_required }
  );
  return response.data;
}

export interface SandboxSnapshot {
  id: string;
  label: string;
  size_bytes: number;
  created_at: string;
}

export async function fetchSandboxSnapshots(sessionId: string) {
  const response = await apiClient.get<{ snapshots: SandboxSnapshot[] }>(
    `/sandbox/sessions/${encodeURIComponent(sessionId)}/snapshots/`
  );
  return response.data.snapshots;
}

export async function createSandboxSnapshot(sessionId: string, label: string) {
  await ensureCsrfToken();
  const response = await apiClient.post<SandboxSnapshot>(
    `/sandbox/sessions/${encodeURIComponent(sessionId)}/snapshots/`,
    { label }
  );
  return response.data;
}
