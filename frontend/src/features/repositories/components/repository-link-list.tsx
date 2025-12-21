import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { deleteRepositoryLink, RepositoryLink } from "@/lib/api-client";

interface RepositoryLinkListProps {
  links?: RepositoryLink[];
  isLoading: boolean;
}

export function RepositoryLinkList({ links, isLoading }: RepositoryLinkListProps) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: deleteRepositoryLink,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["repository-links"] });
    }
  });

  const handleDelete = (id: string) => {
    mutation.mutate(id);
  };

  return (
    <Card className="home-card home-ring-soft border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
      <CardHeader>
        <CardTitle className="text-lg font-semibold text-white">Linked repositories</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {[0, 1, 2].map((index) => (
              <Skeleton key={index} className="h-12 w-full" />
            ))}
          </div>
        ) : !links || links.length === 0 ? (
          <p className="text-sm text-zinc-300">
            No repositories linked yet. Add one above to enable automated merge requests.
          </p>
        ) : (
          <ul className="space-y-3">
            {links.map((link) => (
              <li
                key={link.id}
                className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-100 md:flex-row md:items-center md:justify-between"
              >
                <div>
                  <div className="font-medium text-white">
                    {link.provider === "gitlab" ? "GitLab" : "GitHub"} • {link.repository}
                  </div>
                  <div className="text-xs text-zinc-400">
                    Base URL: {link.base_url ? link.base_url : "default"} • Token: {link.token_preview}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-rose-200 hover:bg-rose-500/10 hover:text-white"
                  onClick={() => handleDelete(link.id)}
                  disabled={mutation.isPending && mutation.variables === link.id}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        )}
        {mutation.isError && (
          <p className="mt-3 text-sm text-destructive">
            Failed to remove the repository. Please try again.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
