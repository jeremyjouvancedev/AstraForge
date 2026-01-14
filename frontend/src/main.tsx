import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { Suspense } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import AppRouter from "@/app/router";
import { AuthProvider } from "@/lib/auth";
import { WorkspaceProvider } from "@/features/workspaces/workspace-context";
import "@/styles/globals.css";
import { Toaster } from "@/components/ui/sonner";

if (typeof document !== "undefined") {
  const rootElement = document.documentElement;
  rootElement.classList.add("dark");
  rootElement.style.colorScheme = "dark";
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000
    }
  }
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <BrowserRouter>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <WorkspaceProvider>
          <Suspense fallback={<div className="p-6">Loading AstraForge...</div>}>
            <AppRouter />
          </Suspense>
        </WorkspaceProvider>
      </AuthProvider>
      <Toaster position="top-right" richColors />
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  </BrowserRouter>
);
