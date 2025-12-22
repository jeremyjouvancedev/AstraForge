import { NavLink } from "react-router-dom";
import {
  BarChart3,
  Brain,
  History,
  Inbox,
  KeyRound,
  LayoutDashboard,
  Link2,
  Sparkles,
  LogOut
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { WorkspaceSwitcher } from "@/features/workspaces/components/workspace-switcher";

const navItems = [
  { to: "/app", label: "Overview", icon: LayoutDashboard, exact: true },
  { to: "/app/activity-logs", label: "Activity logs", icon: History },
  { to: "/app/usage", label: "Usage", icon: BarChart3 },
  { to: "/app/requests", label: "Requests", icon: Inbox },
  { to: "/app/repositories", label: "Repositories", icon: Link2 },
  { to: "/app/api-keys", label: "API Keys", icon: KeyRound },
  { to: "/app/deep-sandbox", label: "Deep Agent Sandbox", icon: Brain }
];

export function Sidebar() {
  const { logout } = useAuth();

  return (
    <aside className="relative hidden h-full w-64 flex-col overflow-y-auto overflow-x-hidden border-r border-sidebar-border/70 bg-sidebar-background/90 pb-4 text-sidebar-foreground shadow-xl shadow-primary/10 lg:flex">
      <div className="relative flex items-center gap-3 px-4 pb-4 pt-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-sidebar-primary/15 text-sidebar-primary ring-1 ring-sidebar-border/80">
          <Sparkles className="h-5 w-5" />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-semibold">AstraForge</p>
          <p className="text-[11px] uppercase tracking-[0.35em] text-sidebar-foreground/60">
            Platform
          </p>
        </div>
      </div>

      <div className="relative px-3 pb-4">
        <WorkspaceSwitcher />
      </div>

      <nav className="relative mt-2 flex flex-1 flex-col gap-1 px-3">
        <p className="px-2 text-[11px] font-semibold uppercase tracking-[0.3em] text-sidebar-foreground/60">
          Navigate
        </p>
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.exact}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition",
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-inner shadow-sidebar-border/40"
                    : "text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
                )
              }
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          );
        })}
      </nav>

      <div className="relative mt-6 px-3">
        <div className="flex items-center justify-between rounded-xl border border-sidebar-border/80 bg-sidebar-background/70 px-3 py-2 text-sm text-sidebar-foreground/80">
          <div>
            <p className="text-[11px] uppercase tracking-[0.3em] text-sidebar-foreground/60">
              Session
            </p>
            <p className="text-sm font-medium text-sidebar-foreground">Signed in</p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-lg text-sidebar-foreground hover:bg-sidebar-accent/60"
            onClick={async () => {
              await logout();
              window.location.href = "/login";
            }}
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </aside>
  );
}
