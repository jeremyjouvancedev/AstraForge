import { Outlet } from "react-router-dom";

import { Sidebar } from "@/components/sidebar";

export default function ShellLayout() {
  return (
    <div className="flex min-h-screen w-full overflow-hidden bg-background text-foreground">
      <Sidebar />
      <main className="flex-1 min-w-0 overflow-x-hidden overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
