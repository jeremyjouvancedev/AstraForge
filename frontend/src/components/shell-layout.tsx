import { Outlet } from "react-router-dom";

import { Sidebar } from "@/components/sidebar";

export default function ShellLayout() {
  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
