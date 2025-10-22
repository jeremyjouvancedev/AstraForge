import { NewRequestForm } from "@/features/requests/components/new-request-form";
import { RequestsTable } from "@/features/requests/components/requests-table";
import { useRequests } from "@/features/requests/hooks/use-requests";

export default function RequestsPage() {
  const { data, isLoading } = useRequests();

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <NewRequestForm />
      <section>
        <header className="mb-4">
          <h2 className="text-lg font-semibold">Request Inbox</h2>
          <p className="text-sm text-muted-foreground">
            Track requests flowing through the AstraForge orchestration lifecycle.
          </p>
        </header>
        <RequestsTable data={data} isLoading={isLoading} />
      </section>
    </div>
  );
}
