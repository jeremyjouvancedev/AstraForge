import { lazy } from "react";
import { Navigate, RouteObject, useRoutes } from "react-router-dom";

import ShellLayout from "@/components/shell-layout";
import { useAuth } from "@/lib/auth";

const RequestsPage = lazy(() => import("@/features/requests/pages/requests-page"));
const RequestThreadPage = lazy(() => import("@/features/chat/pages/request-thread-page"));
const RunsPage = lazy(() => import("@/features/runs/pages/runs-page"));
const MergeRequestsPage = lazy(() => import("@/features/mr/pages/mr-dashboard-page"));
const LoginPage = lazy(() => import("@/features/auth/pages/login-page"));
const RegisterPage = lazy(() => import("@/features/auth/pages/register-page"));

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
      { path: "/requests/:id", element: <RequestThreadPage /> },
      { path: "/runs", element: <RunsPage /> },
      { path: "/merge-requests", element: <MergeRequestsPage /> }
    ]
  },
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  { path: "*", element: <Navigate to="/" replace /> }
];

export default function AppRouter() {
  return useRoutes(routes);
}
