import { lazy } from "react";
import { Navigate, RouteObject, useParams, useRoutes } from "react-router-dom";

import ShellLayout from "@/components/shell-layout";
import { useAuth } from "@/lib/auth";

const HomePage = lazy(() => import("@/features/marketing/pages/home-page"));
const AppOverviewPage = lazy(
  () => import("@/features/overview/pages/app-overview-page")
);
const RequestsPage = lazy(() => import("@/features/requests/pages/requests-page"));
const RequestRunPage = lazy(
  () => import("@/features/requests/pages/request-run-page")
);
const ActivityLogsPage = lazy(
  () => import("@/features/activity/pages/activity-logs-page")
);
const UsagePage = lazy(() => import("@/features/usage/pages/usage-page"));
const LoginPage = lazy(() => import("@/features/auth/pages/login-page"));
const RegisterPage = lazy(() => import("@/features/auth/pages/register-page"));
const RepositoryLinksPage = lazy(
  () => import("@/features/repositories/pages/repository-links-page")
);
const ApiKeysPage = lazy(() => import("@/features/api-keys/pages/api-keys-page"));
const DeepAgentSandboxPage = lazy(
  () => import("@/features/deepagent/pages/deepagent-sandbox-page")
);

function ProtectedShell() {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center">Loading...</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <ShellLayout />;
}

function LegacyRequestRunRedirect() {
  const { id } = useParams<{ id: string }>();
  const target = id ? `/app/requests/${id}/run` : "/app/requests";
  return <Navigate to={target} replace />;
}

const routes: RouteObject[] = [
  {
    path: "/",
    element: <HomePage />
  },
  {
    path: "/app",
    element: <ProtectedShell />,
    children: [
      { index: true, element: <AppOverviewPage /> },
      { path: "activity-logs", element: <ActivityLogsPage /> },
      { path: "usage", element: <UsagePage /> },
      { path: "requests", element: <RequestsPage /> },
      { path: "requests/:id/run", element: <RequestRunPage /> },
      { path: "runs", element: <Navigate to="/app" replace /> },
      { path: "merge-requests", element: <Navigate to="/app" replace /> },
      { path: "repositories", element: <RepositoryLinksPage /> },
      { path: "api-keys", element: <ApiKeysPage /> },
      { path: "deep-sandbox", element: <DeepAgentSandboxPage /> }
    ]
  },
  { path: "/requests", element: <Navigate to="/app/requests" replace /> },
  { path: "/requests/:id/run", element: <LegacyRequestRunRedirect /> },
  { path: "/activity-logs", element: <Navigate to="/app/activity-logs" replace /> },
  { path: "/usage", element: <Navigate to="/app/usage" replace /> },
  { path: "/repositories", element: <Navigate to="/app/repositories" replace /> },
  { path: "/api-keys", element: <Navigate to="/app/api-keys" replace /> },
  { path: "/deep-sandbox", element: <Navigate to="/app/deep-sandbox" replace /> },
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  { path: "*", element: <Navigate to="/" replace /> }
];

export default function AppRouter() {
  return useRoutes(routes);
}
