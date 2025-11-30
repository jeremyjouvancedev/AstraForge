import { lazy } from "react";
import { Navigate, RouteObject, useRoutes } from "react-router-dom";

import ShellLayout from "@/components/shell-layout";
import { useAuth } from "@/lib/auth";

const RequestsPage = lazy(() => import("@/features/requests/pages/requests-page"));
const RequestRunPage = lazy(
  () => import("@/features/requests/pages/request-run-page")
);
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

const routes: RouteObject[] = [
  {
    path: "/",
    element: <ProtectedShell />,
    children: [
      { index: true, element: <RequestsPage /> },
      { path: "/requests/:id/run", element: <RequestRunPage /> },
      { path: "/runs", element: <Navigate to="/" replace /> },
      { path: "/merge-requests", element: <Navigate to="/" replace /> },
      { path: "/repositories", element: <RepositoryLinksPage /> },
      { path: "/api-keys", element: <ApiKeysPage /> },
      { path: "/deep-sandbox", element: <DeepAgentSandboxPage /> }
    ]
  },
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  { path: "*", element: <Navigate to="/" replace /> }
];

export default function AppRouter() {
  return useRoutes(routes);
}
