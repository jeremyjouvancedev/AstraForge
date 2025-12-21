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
  const inputClassName =
    "rounded-xl border-white/10 bg-black/30 text-zinc-100 ring-1 ring-white/5 placeholder:text-zinc-500 focus-visible:border-indigo-400/60 focus-visible:ring-indigo-400/60 focus-visible:ring-offset-0";

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
    <div className="mx-auto flex max-w-4xl flex-col gap-6 p-6 text-zinc-100">
      <header className="home-card home-ring-soft space-y-2 rounded-2xl border border-white/10 bg-black/30 p-6 shadow-lg shadow-indigo-500/15 backdrop-blur">
        <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-indigo-200/80">
          Programmatic access
        </p>
        <h1 className="text-2xl font-semibold text-white">API Keys</h1>
        <p className="text-sm text-zinc-300">
          Create and manage API keys for authenticating external clients. Keys are shown once on creation.
        </p>
      </header>

      <Card className="home-card home-ring-soft border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
        <CardHeader>
          <CardTitle className="text-base font-semibold text-white">Create new key</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              placeholder="Key name (e.g., CI pipeline)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={inputClassName}
              disabled={createKey.isPending}
            />
            <Button variant="brand" className="rounded-xl" onClick={handleCreate} disabled={!name.trim() || createKey.isPending}>
              {createKey.isPending ? "Creating..." : "Create key"}
            </Button>
          </div>
          {newKey && (
            <div className="rounded-xl border border-dashed border-indigo-300/60 bg-indigo-500/5 p-3 text-sm text-zinc-100">
              <p className="font-semibold text-white">Save this key now:</p>
              <code className="mt-2 block overflow-auto rounded-lg bg-black/50 px-3 py-2 text-xs text-indigo-100">
                {newKey}
              </code>
              <p className="mt-2 text-xs text-zinc-300">
                This value will not be shown again. Store it in your secrets manager.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="home-card home-ring-soft border-white/10 bg-black/30 text-zinc-100 shadow-lg shadow-indigo-500/15 backdrop-blur">
        <CardHeader>
          <CardTitle className="text-base font-semibold text-white">Existing keys</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {isLoading ? (
            <p className="text-sm text-zinc-300">Loading keys…</p>
          ) : sortedKeys.length === 0 ? (
            <p className="text-sm text-zinc-300">No API keys yet. Create one above.</p>
          ) : (
            <div className="overflow-hidden rounded-2xl border border-white/10 bg-black/20">
              <table className="min-w-full text-left text-sm text-zinc-100">
                <thead className="bg-white/5 text-zinc-300">
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
                      <tr key={key.id} className="border-t border-white/10">
                        <td className="px-3 py-2 font-medium text-white">{key.name}</td>
                        <td className="px-3 py-2 text-zinc-300">{created}</td>
                        <td className="px-3 py-2 text-zinc-300">{lastUsed}</td>
                        <td className="px-3 py-2">
                          {key.is_active ? (
                            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-200 ring-1 ring-emerald-300/40">
                              Active
                            </span>
                          ) : (
                            <span className="rounded-full bg-white/10 px-2 py-0.5 text-xs font-semibold text-zinc-400 ring-1 ring-white/10">
                              Revoked
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right">
                          {key.is_active ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-rose-200 hover:bg-rose-500/10 hover:text-white"
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
