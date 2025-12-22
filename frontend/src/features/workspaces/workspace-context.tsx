import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { useAuth } from "@/lib/auth";
import { createWorkspace as apiCreateWorkspace, fetchWorkspaces } from "@/lib/api-client";
import { toast } from "@/components/ui/sonner";

export type Workspace = {
  uid: string;
  name: string;
  role?: string;
  accentColor?: string;
};

export type WorkspaceContextValue = {
  workspaces: Workspace[];
  activeWorkspace: Workspace | null;
  selectWorkspace: (uid: string) => void;
  createWorkspace: (name: string) => Promise<Workspace | null>;
  loading: boolean;
};

const ACTIVE_WORKSPACE_KEY = "astraforge.active-workspace";

function colorFromString(seed: string): string {
  const palette = ["#6366F1", "#22D3EE", "#F97316", "#10B981", "#D946EF", "#0EA5E9"];
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash << 5) - hash + seed.charCodeAt(i);
    hash |= 0;
  }
  const index = Math.abs(hash) % palette.length;
  return palette[index];
}

function loadActiveWorkspaceUid(fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const stored = window.localStorage.getItem(ACTIVE_WORKSPACE_KEY);
  return stored || fallback;
}

export const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(undefined);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeWorkspaceUid, setActiveWorkspaceUid] = useState<string>(() =>
    loadActiveWorkspaceUid("tenant-default")
  );
  const [loading, setLoading] = useState<boolean>(false);

  const loadWorkspaces = async () => {
    if (!user) {
      setWorkspaces([]);
      return;
    }
    setLoading(true);
    try {
      const data = await fetchWorkspaces();
      const mapped =
        data?.map((entry) => ({
          uid: entry.uid,
          name: entry.name || entry.uid,
          role: entry.role,
          accentColor: colorFromString(entry.uid)
        })) ?? [];
      setWorkspaces(mapped);
    } catch {
      toast.error("Unable to load workspaces", {
        description: "Check your connection and try again."
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadWorkspaces();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.username]);

  useEffect(() => {
    const allowed = workspaces.map((workspace) => workspace.uid);
    if (allowed.length === 0) {
      setActiveWorkspaceUid("tenant-default");
      return;
    }
    const preferred =
      allowed.includes(activeWorkspaceUid) && activeWorkspaceUid
        ? activeWorkspaceUid
        : allowed.includes(user?.default_workspace || "")
          ? (user?.default_workspace as string)
          : allowed[0];
    if (preferred !== activeWorkspaceUid) {
      setActiveWorkspaceUid(preferred);
    }
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ACTIVE_WORKSPACE_KEY, preferred);
    }
  }, [activeWorkspaceUid, workspaces, user?.default_workspace]);

  const activeWorkspace = useMemo(() => {
    if (workspaces.length === 0) return null;
    return workspaces.find((workspace) => workspace.uid === activeWorkspaceUid) ?? workspaces[0];
  }, [activeWorkspaceUid, workspaces]);

  const selectWorkspace = (uid: string) => {
    const exists = workspaces.find((workspace) => workspace.uid === uid);
    if (!exists) return;
    setActiveWorkspaceUid(uid);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ACTIVE_WORKSPACE_KEY, uid);
    }
  };

  const createWorkspace = async (name: string) => {
    if (!name.trim()) return null;
    try {
      const created = await apiCreateWorkspace({ name });
      await loadWorkspaces();
      selectWorkspace(created.uid);
      toast.success("Workspace created", {
        description: `${created.name} is ready to use.`
      });
      return {
        uid: created.uid,
        name: created.name,
        role: created.role,
        accentColor: colorFromString(created.uid)
      };
    } catch {
      toast.error("Unable to create workspace", {
        description: "You might not have permission to create workspaces."
      });
      return null;
    }
  };

  const value: WorkspaceContextValue = {
    workspaces,
    activeWorkspace,
    selectWorkspace,
    createWorkspace,
    loading
  };

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error("useWorkspace must be used within a WorkspaceProvider");
  }
  return context;
}
