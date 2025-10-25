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
  metadata?: Record<string, unknown>;
  artifacts?: Record<string, unknown>;
}

export interface CreateRequestInput {
  title: string;
  description: string;
  context?: string;
  projectId: string;
}

export async function createRequest(input: CreateRequestInput) {
  const payload: ApiRequestPayload = {
    title: input.title,
    description: input.description,
    context: input.context ? { notes: input.context } : {},
  };

  const response = await apiClient.post<CreateRequestResponse>("/requests/", {
    source: "direct_user",
    tenant_id: "tenant-default",
    sender: "user@example.com",
    project_id: input.projectId,
    payload,
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
  const response = await apiClient.post<RepositoryLink>("/repository-links/", payload);
  return response.data;
}

export async function deleteRepositoryLink(id: string) {
  await apiClient.delete(`/repository-links/${id}/`);
}
