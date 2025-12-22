import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { NewRequestForm } from "@/features/requests/components/new-request-form";
import { RequestsTable } from "@/features/requests/components/requests-table";
import { useRequests } from "@/features/requests/hooks/use-requests";
import { useRepositoryLinks } from "@/features/repositories/hooks/use-repository-links";
import { useWorkspace } from "@/features/workspaces/workspace-context";

export default function RequestsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { activeWorkspace, loading: workspaceLoading } = useWorkspace();
  const workspaceUid = activeWorkspace?.uid;
  const { data: requests, isLoading: requestsLoading } = useRequests(workspaceUid);
  const {
    data: repositoryLinks,
    isLoading: linksLoading,
    isError: linksError
  } = useRepositoryLinks(workspaceUid);
  const repoLinksLoading = workspaceLoading || linksLoading || !workspaceUid;

  const hasProjects = !!workspaceUid && (repositoryLinks?.length ?? 0) > 0;
  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["requests"] });
    queryClient.invalidateQueries({ queryKey: ["repository-links", workspaceUid || "none"] });
  };

  const handleRequestSelect = (requestId: string) => {
    navigate(`/app/requests/${requestId}/run`);
  };

  return (
    <div className="relative z-10 mx-auto w-full max-w-6xl space-y-8 px-4 py-8 sm:px-6 lg:px-10 text-zinc-100">
      <section className="home-card home-ring-soft rounded-3xl border border-white/10 bg-black/30 p-8 shadow-2xl shadow-indigo-500/15 backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-indigo-200/80">
              AstraForge Workspace
            </p>
            <h1 className="mt-2 text-3xl font-semibold text-white">Request Inbox</h1>
            <p className="mt-3 max-w-2xl text-sm text-zinc-300">
              Capture product intent, batch automations, and let the Codex Engine land the change safely in your repositories.
            </p>
          </div>
          <div className="flex flex-col items-start gap-3 text-sm text-zinc-300">
            <span className="text-xs uppercase tracking-[0.3em] text-indigo-200/80">Queue Size</span>
            <Badge variant="secondary" className="rounded-full border border-white/10 bg-white/10 px-4 py-1 text-sm text-white">
              {requests?.length ?? 0} Active
            </Badge>
            <Button variant="outline" size="sm" asChild className="rounded-xl border-white/20 text-white hover:border-indigo-300/60 hover:text-indigo-100">
              <Link to="/app/repositories">Manage repositories</Link>
            </Button>
          </div>
        </div>
      </section>

      {repoLinksLoading ? (
        <Card className="home-card home-ring-soft rounded-2xl border border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
          <CardHeader>
            <CardTitle>Checking project access...</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-zinc-300">
              Loading linked projects. You can submit requests once at least one project is ready.
            </p>
          </CardContent>
        </Card>
      ) : linksError ? (
        <Card className="home-card home-ring-soft rounded-2xl border border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
          <CardHeader>
            <CardTitle>Unable to load projects</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-destructive">
              We couldn't verify linked projects. Refresh the page or try again later.
            </p>
          </CardContent>
        </Card>
      ) : hasProjects ? (
        <NewRequestForm projects={repositoryLinks ?? []} />
      ) : (
        <Card className="home-card home-ring-soft rounded-2xl border border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
          <CardHeader>
            <CardTitle>No projects linked yet</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-zinc-300">
              Add at least one project so AstraForge knows where to deliver automated work.
            </p>
            <Button asChild variant="brand" size="sm" className="rounded-xl">
              <Link to="/app/repositories">Link a project</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      <section className="home-card home-ring-soft rounded-3xl border border-white/10 bg-black/30 shadow-2xl shadow-indigo-500/15 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 px-6 py-5">
          <div>
            <h2 className="text-lg font-semibold text-white">Recent Requests</h2>
            <p className="text-sm text-zinc-300">
              Track requests flowing through the AstraForge orchestration lifecycle.
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="rounded-full px-4 text-zinc-300 hover:bg-white/5"
            onClick={handleRefresh}
          >
            Refresh
          </Button>
        </div>
        <div className="p-6">
          <RequestsTable
            data={requests}
            isLoading={requestsLoading}
            onSelect={(request) => handleRequestSelect(request.id)}
          />
        </div>
      </section>
    </div>
  );
}
