import { Outlet } from "react-router-dom";

import BrandSurface from "@/components/brand-surface";
import { Sidebar } from "@/components/sidebar";

export default function ShellLayout() {
  return (
    <BrandSurface contentClassName="flex h-screen w-full overflow-hidden" glow="soft">
      <Sidebar />
      <div className="relative z-10 flex h-full flex-1 flex-col overflow-hidden">
        <main className="relative z-10 flex-1 min-w-0 overflow-x-hidden overflow-y-auto bg-transparent">
          <Outlet />
        </main>
      </div>
    </BrandSurface>
  );
}
