import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NewRequestForm } from "@/features/requests/components/new-request-form";
import { RequestsTable } from "@/features/requests/components/requests-table";
import { useRequests } from "@/features/requests/hooks/use-requests";
import { useRepositoryLinks } from "@/features/repositories/hooks/use-repository-links";

export default function RequestsPage() {
  const navigate = useNavigate();

  const { data: requests, isLoading: requestsLoading } = useRequests();
  const {
    data: repositoryLinks,
    isLoading: linksLoading,
    isError: linksError
  } = useRepositoryLinks();

  const hasProjects = (repositoryLinks?.length ?? 0) > 0;

  const handleRequestSelect = (requestId: string) => {
    navigate(`/requests/${requestId}/run`);
  };

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 p-6">
      <header className="space-y-1">
        <p className="text-xs uppercase tracking-[0.3em] text-muted-foreground">
          AstraForge Workspace
        </p>
        <h1 className="text-2xl font-semibold">Request Inbox</h1>
      </header>

      {linksLoading ? (
        <Card>
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
        <Card>
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
        <Card>
          <CardHeader>
            <CardTitle>No projects linked yet</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Add at least one project so AstraForge knows where to deliver automated work.
            </p>
            <Button asChild variant="outline" size="sm">
              <Link to="/repositories">Link a project</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      <section>
        <header className="mb-4">
          <h2 className="text-lg font-semibold">Recent Requests</h2>
          <p className="text-sm text-muted-foreground">
            Track requests flowing through the AstraForge orchestration lifecycle.
          </p>
        </header>
        <RequestsTable
          data={requests}
          isLoading={requestsLoading}
          onSelect={(request) => handleRequestSelect(request.id)}
        />
      </section>
    </div>
  );
}
