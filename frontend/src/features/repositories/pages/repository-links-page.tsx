import { RepositoryLinkForm } from "@/features/repositories/components/repository-link-form";
import { RepositoryLinkList } from "@/features/repositories/components/repository-link-list";
import { useRepositoryLinks } from "@/features/repositories/hooks/use-repository-links";
import { useWorkspace } from "@/features/workspaces/workspace-context";

export default function RepositoryLinksPage() {
  const { activeWorkspace, loading: workspaceLoading } = useWorkspace();
  const workspaceUid = activeWorkspace?.uid;
  const { data, isLoading } = useRepositoryLinks(workspaceUid);
  const loadingState = workspaceLoading || isLoading || !workspaceUid;

  return (
    <div className="mx-auto flex max-w-[clamp(56rem,72vw,96rem)] flex-col gap-6 p-6 text-zinc-100">
      <header className="home-card home-ring-soft space-y-2 rounded-2xl border border-white/10 bg-black/30 p-6 shadow-lg shadow-indigo-500/15 backdrop-blur">
        <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-indigo-200/80">
          Trusted sources
        </p>
        <h1 className="text-2xl font-semibold text-white">Repository Links</h1>
        <p className="text-sm text-zinc-300">
          Connect GitLab or GitHub repositories so AstraForge can open merge requests with your
          credentials.
        </p>
      </header>
      <RepositoryLinkForm />
      <RepositoryLinkList
        links={data}
        isLoading={loadingState}
        workspaceUid={workspaceUid}
      />
    </div>
  );
}
