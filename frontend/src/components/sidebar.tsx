import { NavLink } from "react-router-dom";
import { Brain, Inbox, KeyRound, Link2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/", label: "Requests", icon: Inbox, exact: true },
  { to: "/repositories", label: "Repositories", icon: Link2 },
  { to: "/api-keys", label: "API Keys", icon: KeyRound },
  { to: "/deep-sandbox", label: "Deep Agent Sandbox", icon: Brain }
];

export function Sidebar() {
  const { logout } = useAuth();

  return (
    <aside className="relative hidden h-full w-72 flex-col overflow-y-auto border-r border-sidebar-border bg-sidebar-background/95 pb-6 text-sidebar-foreground shadow-2xl shadow-primary/5 lg:flex">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-70"
        style={{
          background:
            "radial-gradient(circle at top, rgba(61,110,255,0.25), transparent 55%)",
        }}
      />

      <div className="relative border-b border-sidebar-border/70 px-6 pb-6 pt-8">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-sidebar-primary/20 text-sidebar-primary">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <p className="text-lg font-semibold">AstraForge</p>
            <p className="text-[10px] uppercase tracking-[0.4em] text-sidebar-foreground/70">
              Platform
            </p>
          </div>
        </div>
        <p className="mt-4 text-sm text-sidebar-foreground/80">
          AI DevOps workspace tuned for enterprise velocity.
        </p>
        <Button variant="default" size="sm" className="mt-4 w-full rounded-2xl" asChild>
          <NavLink to="/">Start a Request</NavLink>
        </Button>
      </div>

      <nav className="relative mt-6 flex flex-1 flex-col gap-1 px-4">
        <p className="px-2 text-xs font-semibold uppercase tracking-[0.3em] text-sidebar-foreground/60">
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
                  "flex items-center gap-3 rounded-2xl px-3.5 py-2.5 text-sm font-medium transition",
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-inner shadow-sidebar-border/40"
                    : "text-sidebar-foreground/70 hover:bg-sidebar-accent/70 hover:text-sidebar-foreground"
                )
              }
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          );
        })}
      </nav>

      <div className="relative mt-8 px-6">
        <div className="rounded-2xl border border-sidebar-border/80 bg-sidebar-accent/40 p-4 text-sm text-sidebar-foreground/80">
          <p className="text-[10px] font-semibold uppercase tracking-[0.35em] text-sidebar-foreground/70">
            Session
          </p>
          <p className="mt-2 text-sidebar-foreground">
            Signed in via AstraForge Auth. Sign out to switch accounts.
          </p>
          <Button
            variant="ghost"
            size="sm"
            className="mt-3 w-full justify-center rounded-xl border border-transparent px-3 text-sidebar-foreground hover:border-sidebar-border/80 hover:bg-sidebar-background/40"
            onClick={async () => {
              await logout();
              window.location.href = "/login";
            }}
          >
            Sign out
          </Button>
        </div>
      </div>
    </aside>
  );
}
