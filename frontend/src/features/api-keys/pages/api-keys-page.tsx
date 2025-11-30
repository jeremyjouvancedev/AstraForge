import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useCreateApiKey, useApiKeys, useRevokeApiKey } from "@/features/api-keys/hooks/use-api-keys";

export default function ApiKeysPage() {
  const { data, isLoading } = useApiKeys();
  const createKey = useCreateApiKey();
  const revokeKey = useRevokeApiKey();
  const [name, setName] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);

  const sortedKeys = useMemo(
    () => (data || []).slice().sort((a, b) => (b.created_at || "").localeCompare(a.created_at || "")),
    [data]
  );

  const handleCreate = async () => {
    if (!name.trim()) return;
    const result = await createKey.mutateAsync(name.trim());
    setName("");
    setNewKey(result.key ?? null);
  };

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold">API Keys</h1>
        <p className="text-sm text-muted-foreground">
          Create and manage API keys for authenticating external clients. Keys are shown once on creation.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">Create new key</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              placeholder="Key name (e.g., CI pipeline)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={createKey.isPending}
            />
            <Button onClick={handleCreate} disabled={!name.trim() || createKey.isPending}>
              {createKey.isPending ? "Creating..." : "Create key"}
            </Button>
          </div>
          {newKey && (
            <div className="rounded-md border border-dashed border-primary/50 bg-primary/5 p-3 text-sm">
              <p className="font-semibold">Save this key now:</p>
              <code className="mt-1 block overflow-auto rounded bg-background px-2 py-1 text-xs">
                {newKey}
              </code>
              <p className="mt-1 text-xs text-muted-foreground">
                This value will not be shown again. Store it in your secrets manager.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">Existing keys</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading keys…</p>
          ) : sortedKeys.length === 0 ? (
            <p className="text-sm text-muted-foreground">No API keys yet. Create one above.</p>
          ) : (
            <div className="overflow-hidden rounded-lg border">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-muted/50 text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-semibold">Name</th>
                    <th className="px-3 py-2 font-semibold">Created</th>
                    <th className="px-3 py-2 font-semibold">Last used</th>
                    <th className="px-3 py-2 font-semibold">Status</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {sortedKeys.map((key) => {
                    const created = key.created_at
                      ? new Date(key.created_at).toLocaleString()
                      : "—";
                    const lastUsed = key.last_used_at
                      ? new Date(key.last_used_at).toLocaleString()
                      : "Never";
                    return (
                      <tr key={key.id} className="border-t">
                        <td className="px-3 py-2">{key.name}</td>
                        <td className="px-3 py-2 text-muted-foreground">{created}</td>
                        <td className="px-3 py-2 text-muted-foreground">{lastUsed}</td>
                        <td className="px-3 py-2">
                          {key.is_active ? (
                            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                              Active
                            </span>
                          ) : (
                            <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-semibold text-muted-foreground">
                              Revoked
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right">
                          {key.is_active ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={revokeKey.isPending}
                              onClick={() => revokeKey.mutate(key.id)}
                            >
                              Revoke
                            </Button>
                          ) : (
                            <span className="text-xs text-muted-foreground">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
