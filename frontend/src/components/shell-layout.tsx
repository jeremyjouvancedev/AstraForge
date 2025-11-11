import { Outlet } from "react-router-dom";

import { Sidebar } from "@/components/sidebar";

export default function ShellLayout() {
  return (
    <div className="flex h-screen w-full overflow-hidden bg-background text-foreground">
      <Sidebar />
      <div className="relative flex h-full flex-1 flex-col overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 -z-10"
          style={{
            background:
              "radial-gradient(circle at 20% -10%, rgba(61,110,255,0.22), transparent 45%), radial-gradient(circle at 80% 0%, rgba(16,185,129,0.15), transparent 40%)",
          }}
        />
        <main className="relative flex-1 min-w-0 overflow-x-hidden overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
