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

export interface CreateRequestResponse {
  id: string;
  state: string;
  payload: ApiRequestPayload;
}

export async function createRequest(payload: ApiRequestPayload) {
  const response = await apiClient.post<CreateRequestResponse>("/requests/", {
    source: "direct_user",
    tenant_id: "tenant-default",
    sender: "user@example.com",
    payload
  });
  return response.data;
}

export async function fetchRequests() {
  const response = await apiClient.get<CreateRequestResponse[]>("/requests/");
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
