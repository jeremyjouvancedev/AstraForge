import { useMemo, useState } from "react";
import { Check, ChevronDown, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/features/workspaces/workspace-context";

export function WorkspaceSwitcher() {
  const { activeWorkspace, workspaces, selectWorkspace, createWorkspace, loading } =
    useWorkspace();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState("");

  const selectedWorkspace = useMemo(
    () => activeWorkspace ?? workspaces[0] ?? null,
    [activeWorkspace, workspaces]
  );

  return (
    <div className="flex flex-col gap-2 text-sidebar-foreground">
      <p className="px-1 text-[11px] font-semibold uppercase tracking-[0.3em] text-sidebar-foreground/60">
        Workspace
      </p>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            className="flex w-full min-w-0 items-center justify-between gap-2 rounded-xl border border-sidebar-border/80 bg-sidebar-background/70 px-3 py-2.5 text-sm font-semibold text-sidebar-foreground hover:bg-sidebar-accent/60"
            disabled={loading || workspaces.length === 0}
          >
            <span className="flex min-w-0 items-center gap-2">
              <span
                aria-hidden
                className="h-3 w-3 rounded-full"
                style={{
                  backgroundColor: selectedWorkspace?.accentColor || "#6366F1"
                }}
              />
              <span className="truncate" title={selectedWorkspace?.name}>
                {loading
                  ? "Loading..."
                  : selectedWorkspace?.name || "No workspace available"}
              </span>
            </span>
            <ChevronDown className="h-4 w-4 opacity-70" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-64">
          <DropdownMenuLabel className="text-xs uppercase tracking-[0.25em] text-muted-foreground">
            Select workspace
          </DropdownMenuLabel>
          {workspaces.length === 0 ? (
            <DropdownMenuItem disabled>No workspaces available</DropdownMenuItem>
          ) : null}
          {workspaces.map((workspace) => (
            <DropdownMenuItem
              key={workspace.uid}
              className={cn(
                "flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm",
                selectedWorkspace?.uid === workspace.uid
                  ? "bg-muted/60 text-foreground"
                  : "text-muted-foreground"
              )}
              onSelect={() => {
                selectWorkspace(workspace.uid);
              }}
            >
              <span className="flex min-w-0 items-center gap-2">
                <span
                  aria-hidden
                  className="h-3 w-3 rounded-full"
                  style={{ backgroundColor: workspace.accentColor || "#4F46E5" }}
                />
                <span className="truncate" title={workspace.name}>
                  {workspace.name}
                </span>
              </span>
              {selectedWorkspace?.uid === workspace.uid ? (
                <Check className="h-4 w-4 text-primary" aria-label="Active workspace" />
              ) : null}
            </DropdownMenuItem>
          ))}
          <DropdownMenuItem
            className="mt-1 flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-foreground"
            onSelect={() => {
              setDialogOpen(true);
            }}
          >
            <Plus className="h-4 w-4" />
            Create workspace
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create workspace</DialogTitle>
            <DialogDescription>
              Give your workspace a name. You will be added as the owner automatically.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <label className="space-y-1 text-sm font-medium text-foreground">
              Name
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Customer A"
              />
            </label>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={async () => {
                const created = await createWorkspace(name);
                if (created) {
                  setDialogOpen(false);
                  setName("");
                }
              }}
              disabled={!name.trim()}
            >
              Create & switch
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
