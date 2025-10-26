import { RepositoryLinkForm } from "@/features/repositories/components/repository-link-form";
import { RepositoryLinkList } from "@/features/repositories/components/repository-link-list";
import { useRepositoryLinks } from "@/features/repositories/hooks/use-repository-links";

export default function RepositoryLinksPage() {
  const { data, isLoading } = useRepositoryLinks();

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold">Repository Links</h1>
        <p className="text-sm text-muted-foreground">
          Connect GitLab or GitHub repositories so AstraForge can open merge requests with your
          credentials.
        </p>
      </header>
      <RepositoryLinkForm />
      <RepositoryLinkList links={data} isLoading={isLoading} />
    </div>
  );
}
