import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { NewRequestForm } from "@/features/requests/components/new-request-form";
import { RequestsTable } from "@/features/requests/components/requests-table";
import { useRequests } from "@/features/requests/hooks/use-requests";
import { useRepositoryLinks } from "@/features/repositories/hooks/use-repository-links";

export default function RequestsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: requests, isLoading: requestsLoading } = useRequests();
  const {
    data: repositoryLinks,
    isLoading: linksLoading,
    isError: linksError
  } = useRepositoryLinks();

  const hasProjects = (repositoryLinks?.length ?? 0) > 0;
  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["requests"] });
    queryClient.invalidateQueries({ queryKey: ["repository-links"] });
  };

  const handleRequestSelect = (requestId: string) => {
    navigate(`/requests/${requestId}/run`);
  };

  return (
    <div className="relative mx-auto w-full max-w-6xl space-y-8 px-4 py-8 sm:px-6 lg:px-10">
      <section className="rounded-3xl border border-border/60 bg-card/95 p-8 shadow-xl shadow-primary/10">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.35em] text-muted-foreground">
              AstraForge Workspace
            </p>
            <h1 className="mt-2 text-3xl font-semibold text-foreground">Request Inbox</h1>
            <p className="mt-3 max-w-2xl text-sm text-muted-foreground">
              Capture product intent, batch automations, and let the Codex Engine land the change safely in your repositories.
            </p>
          </div>
          <div className="flex flex-col items-start gap-3 text-sm text-muted-foreground">
            <span className="text-xs uppercase tracking-[0.3em]">Queue Size</span>
            <Badge variant="secondary" className="rounded-full px-4 py-1 text-sm">
              {requests?.length ?? 0} Active
            </Badge>
            <Button variant="outline" size="sm" asChild className="rounded-xl">
              <Link to="/repositories">Manage repositories</Link>
            </Button>
          </div>
        </div>
      </section>

      {linksLoading ? (
        <Card className="rounded-2xl border border-border/60 bg-card/95 shadow-lg">
          <CardHeader>
            <CardTitle>Checking project access...</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Loading linked projects. You can submit requests once at least one project is ready.
            </p>
          </CardContent>
        </Card>
      ) : linksError ? (
        <Card className="rounded-2xl border border-border/60 bg-card/95 shadow-lg">
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
        <Card className="rounded-2xl border border-border/60 bg-card/95 shadow-lg">
          <CardHeader>
            <CardTitle>No projects linked yet</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Add at least one project so AstraForge knows where to deliver automated work.
            </p>
            <Button asChild variant="accent" size="sm" className="rounded-xl">
              <Link to="/repositories">Link a project</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      <section className="rounded-3xl border border-border/60 bg-card/95 shadow-xl shadow-primary/10">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/70 px-6 py-5">
          <div>
            <h2 className="text-lg font-semibold">Recent Requests</h2>
            <p className="text-sm text-muted-foreground">
              Track requests flowing through the AstraForge orchestration lifecycle.
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="rounded-full px-4"
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
