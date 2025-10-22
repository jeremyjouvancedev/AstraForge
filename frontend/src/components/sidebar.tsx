import { NavLink } from "react-router-dom";
import { GitMerge, Inbox, ListChecks } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

const navItems = [
  { to: "/", label: "Requests", icon: Inbox },
  { to: "/runs", label: "Runs", icon: ListChecks },
  { to: "/merge-requests", label: "Merge Requests", icon: GitMerge }
];

export function Sidebar() {
  const { logout } = useAuth();

  return (
    <aside className="flex w-64 flex-col border-r bg-background">
      <div className="p-4">
        <h1 className="text-xl font-semibold">AstraForge</h1>
        <p className="text-sm text-muted-foreground">AI DevOps Orchestrator</p>
      </div>
      <Button variant="outline" className="mx-4" asChild>
        <NavLink to="/" className="w-full">
          New Request
        </NavLink>
      </Button>
      <nav className="mt-4 space-y-1 px-4">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center rounded px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-muted text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`
              }
            >
              <Icon className="mr-2 h-4 w-4" />
              {item.label}
            </NavLink>
          );
        })}
      </nav>
      <div className="mt-auto p-4">
        <Button
          variant="ghost"
          className="w-full justify-start"
          onClick={async () => {
            await logout();
            window.location.href = "/login";
          }}
        >
          Log out
        </Button>
      </div>
    </aside>
  );
}
