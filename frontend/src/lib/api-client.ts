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
      const path = window.location.pathname;
      if (path !== "/login" && path !== "/register") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export type ApiRequestPayload = {
  title: string;
  description: string;
  context?: Record<string, unknown>;
  attachments?: Array<{ uri: string; name: string; content_type: string }>;
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
}

export async function createRequest(input: CreateRequestInput) {
  const response = await apiClient.post<CreateRequestResponse>("/requests/", {
    source: input.source ?? "direct_user",
    tenant_id: input.tenantId ?? "tenant-default",
    sender: input.sender ?? "user@example.com",
    project_id: input.projectId,
    prompt: input.prompt,
  });
  return response.data;
}

export async function fetchRequests() {
  const response = await apiClient.get<CreateRequestResponse[]>("/requests/");
  return response.data;
}

export interface DevelopmentSpecDto {
  title: string;
  summary: string;
  requirements: string[];
  implementation_steps: string[];
  risks: string[];
  acceptance_criteria: string[];
}

export async function fetchRequestDetail(id: string) {
  const response = await apiClient.get<CreateRequestResponse>(`/requests/${id}/`);
  return response.data;
}

export async function sendChatMessage(payload: { requestId: string; message: string }) {
  const response = await apiClient.post<{ status: string }>("/chat/", {
    request_id: payload.requestId,
    message: payload.message
  });
  return response.data;
}

export async function executeRequest(payload: {
  requestId: string;
  spec?: DevelopmentSpecDto;
}) {
  const response = await apiClient.post<{ status: string }>(
    `/requests/${payload.requestId}/execute/`,
    payload.spec ? { spec: payload.spec } : {}
  );
  return response.data;
}

export interface AuthUser {
  username: string;
  email: string;
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

export type RepositoryProvider = "gitlab" | "github";

export interface RepositoryLink {
  id: string;
  provider: RepositoryProvider;
  repository: string;
  base_url?: string | null;
  token_preview: string;
  created_at: string;
  updated_at: string;
}

export interface CreateRepositoryLinkPayload {
  provider: RepositoryProvider;
  repository: string;
  access_token: string;
  base_url?: string;
}

export async function fetchRepositoryLinks() {
  const response = await apiClient.get<RepositoryLink[]>("/repository-links/");
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

// Sandbox sessions ------------------------------------------------------------
export interface SandboxSession {
  id: string;
  mode: string;
  status: string;
  created_at?: string;
  updated_at?: string;
  last_activity_at?: string | null;
}

export async function fetchSandboxSessions() {
  const response = await apiClient.get<SandboxSession[]>("/sandbox/sessions/");
  return response.data;
}
