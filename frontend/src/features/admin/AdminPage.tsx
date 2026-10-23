import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ErrorState, LoadingState } from "@/components/UiState";
import { API_BASE, api } from "@/lib/api";

interface Preview {
  mode: string;
  confirmation_hash: string;
  report: Record<string, unknown>;
}
interface UserRow {
  id: number;
  username: string;
  email: string;
  roles: string[];
}
interface UsersPayload {
  roles: string[];
  results: UserRow[];
}
interface ImportRow {
  id: string;
  kind: string;
  status: string;
  source_filename: string;
  created_at: string;
}

function ImportPanel({
  kind,
  title,
  accept,
}: {
  kind: "seed" | "ppm";
  title: string;
  accept: string;
}) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const hasValidPreview = preview?.mode === "dry-run" && Boolean(preview.confirmation_hash);
  const applyHelpId = `apply-help-${kind}`;
  const upload = useMutation({
    mutationFn: async (apply: boolean) => {
      if (!file) throw new Error("File mancante");
      const form = new FormData();
      form.append("file", file);
      form.append("apply", String(apply));
      if (apply && preview) form.append("confirmation_hash", preview.confirmation_hash);
      return api.post<Preview>(`/admin/imports/${kind}`, form);
    },
    onSuccess: async (result) => {
      setPreview(result);
      await queryClient.invalidateQueries({ queryKey: ["admin", "imports"] });
    },
  });
  return (
    <section className="space-y-3 rounded-lg border border-border bg-card p-4">
      <h2 className="font-medium">{title}</h2>
      <input
        type="file"
        accept={accept}
        onChange={(event) => {
          setFile(event.target.files?.[0] ?? null);
          setPreview(null);
        }}
      />
      <div className="flex flex-wrap items-start gap-4">
        <button
          className="rounded border px-3 py-2 text-sm"
          disabled={!file || upload.isPending}
          onClick={() => upload.mutate(false)}
        >
          Valida e simula
        </button>
        <div className="border-l border-border pl-4">
          <button
            className="rounded-md border-2 border-emerald-800 bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 disabled:cursor-not-allowed disabled:border-slate-400 disabled:bg-slate-200 disabled:text-slate-600 disabled:shadow-none"
            disabled={!hasValidPreview || upload.isPending}
            aria-describedby={applyHelpId}
            onClick={() => upload.mutate(true)}
          >
            Conferma e applica
          </button>
          <p id={applyHelpId} className="mt-1 max-w-xs text-xs text-muted-foreground">
            {hasValidPreview
              ? "Anteprima valida: l'applicazione userà l'hash di conferma mostrato."
              : "Esegui prima “Valida e simula” per abilitare l'applicazione."}
          </p>
        </div>
      </div>
      {upload.isError && (
        <p className="text-destructive text-sm">
          Import non valido. Controllare formato, contenuti e permessi.
        </p>
      )}
      {preview && (
        <pre className="max-h-72 overflow-auto rounded bg-muted p-3 text-xs">
          {JSON.stringify(preview.report, null, 2)}
        </pre>
      )}
    </section>
  );
}

export function AdminPage() {
  const queryClient = useQueryClient();
  const imports = useQuery({
    queryKey: ["admin", "imports"],
    queryFn: () => api.get<{ results: ImportRow[] }>("/admin/imports"),
  });
  const users = useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => api.get<UsersPayload>("/admin/users"),
  });
  const assignRole = useMutation({
    mutationFn: ({ user_id, role }: { user_id: number; role: string }) =>
      api.post("/admin/users", { user_id, role }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
  if (imports.isLoading || users.isLoading) return <LoadingState />;
  if (imports.isError || users.isError || !imports.data || !users.data)
    return <ErrorState title="Amministrazione non disponibile" />;
  return (
    <section className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold">Amministrazione</h1>
        <p className="text-sm text-muted-foreground">
          Import controllati, export e assegnazione ruoli.
        </p>
      </header>
      <div className="grid gap-4 xl:grid-cols-2">
        <ImportPanel kind="seed" title="Import seed JSON" accept="application/json,.json" />
        <ImportPanel kind="ppm" title="Import PPM" accept=".xlsx,.pdf" />
      </div>
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 font-medium">Export</h2>
        <div className="flex flex-wrap gap-2">
          <a className="rounded border px-3 py-2 text-sm" href={`${API_BASE}/export/json`}>
            JSON
          </a>
          <a className="rounded border px-3 py-2 text-sm" href={`${API_BASE}/export/excel`}>
            Excel
          </a>
          <a className="rounded border px-3 py-2 text-sm" href={`${API_BASE}/export/csv/projects`}>
            CSV progetti
          </a>
        </div>
      </section>
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 font-medium">Utenti e ruoli</h2>
        <div className="space-y-2">
          {users.data.results.map((user) => (
            <div
              key={user.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded border p-2 text-sm"
            >
              <span>
                <strong>{user.username}</strong> — {user.email || "email assente"}
              </span>
              <select
                aria-label={`Ruolo di ${user.username}`}
                value={user.roles[0] ?? ""}
                onChange={(event) =>
                  assignRole.mutate({ user_id: user.id, role: event.target.value })
                }
              >
                <option value="">Nessun ruolo</option>
                {users.data.roles.map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      </section>
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 font-medium">Storico import</h2>
        <div className="space-y-2 text-sm">
          {imports.data.results.map((row) => (
            <div key={row.id} className="rounded border p-2">
              <strong>{row.kind}</strong> — {row.status} — {row.source_filename || "senza file"} —{" "}
              {new Date(row.created_at).toLocaleString("it-IT")}
            </div>
          ))}
        </div>
      </section>
      <p className="text-xs text-muted-foreground">
        Gestione password e funzioni Django avanzate restano nel Django admin.
      </p>
    </section>
  );
}
