import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ErrorState, LoadingState } from "@/components/UiState";
import { API_BASE, ApiError, api } from "@/lib/api";

interface Preview {
  mode: string;
  confirmation_hash: string;
  report: Record<string, unknown>;
}
interface RoleOption {
  key: string;
  label: string;
}
interface UserRow {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  roles: string[];
  last_login: string | null;
  date_joined: string;
}
interface UsersPayload {
  roles: RoleOption[];
  results: UserRow[];
}
interface RoleCapability {
  key: string;
  label: string;
  capabilities: string[];
}
interface RolesPayload {
  capabilities: string[];
  reserved: string[];
  roles: RoleCapability[];
}
interface ImportRow {
  id: string;
  kind: string;
  status: string;
  source_filename: string;
  created_at: string;
}
type Tab = "imports" | "users" | "roles";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const fields = Object.values(error.fieldErrors);
    return fields.length ? fields.join(" ") : error.message;
  }
  return error instanceof Error ? error.message : "Operazione non riuscita.";
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
    <section className="rounded-lg border border-border bg-card p-4">
      <h2 className="font-medium">{title}</h2>
      <input
        className="mt-3 block text-sm"
        type="file"
        accept={accept}
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <div className="mt-3 flex gap-2">
        <button
          className="rounded border px-3 py-2 text-sm"
          disabled={!file || upload.isPending}
          onClick={() => upload.mutate(false)}
        >
          Valida e simula
        </button>
        <button
          className="rounded border border-emerald-800 bg-emerald-600 px-3 py-2 text-sm text-white disabled:opacity-50"
          disabled={!file || !hasValidPreview || upload.isPending}
          onClick={() => upload.mutate(true)}
        >
          Conferma e applica
        </button>
      </div>
      {!hasValidPreview && (
        <p className="mt-2 text-xs text-muted-foreground">Esegui prima “Valida e simula”.</p>
      )}
      {upload.isError && (
        <p role="alert" className="text-destructive mt-2 text-sm">
          {errorMessage(upload.error)}
        </p>
      )}
      {preview && (
        <pre className="mt-3 max-h-64 overflow-auto rounded bg-muted p-2 text-xs">
          {JSON.stringify(preview.report, null, 2)}
        </pre>
      )}
    </section>
  );
}

function UserForm({
  roles,
  initial,
  onClose,
  onSaved,
}: {
  roles: RoleOption[];
  initial?: UserRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [username, setUsername] = useState(initial?.username ?? "");
  const [firstName, setFirstName] = useState(initial?.first_name ?? "");
  const [lastName, setLastName] = useState(initial?.last_name ?? "");
  const [email, setEmail] = useState(initial?.email ?? "");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState(initial?.roles[0] ?? roles[0]?.key ?? "");
  const [active, setActive] = useState(initial?.is_active ?? true);
  const mutation = useMutation({
    mutationFn: () => {
      const payload = {
        username,
        first_name: firstName,
        last_name: lastName,
        email,
        roles: role ? [role] : [],
        is_active: active,
        ...(password ? { password } : {}),
      };
      return initial
        ? api.patch(`/admin/users/${initial.id}`, payload)
        : api.post("/admin/users", payload);
    },
    onSuccess: onSaved,
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="user-form-title"
      className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4"
    >
      <form
        onSubmit={submit}
        className="w-full max-w-lg space-y-3 rounded-lg bg-background p-5 shadow-xl"
      >
        <h2 id="user-form-title" className="text-lg font-semibold">
          {initial ? "Modifica utente" : "Crea utente"}
        </h2>
        <label className="block text-sm">
          Username
          <input
            aria-label="Username"
            required
            className="mt-1 w-full rounded border p-2"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            Nome
            <input
              aria-label="Nome"
              className="mt-1 w-full rounded border p-2"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
            />
          </label>
          <label className="text-sm">
            Cognome
            <input
              aria-label="Cognome"
              className="mt-1 w-full rounded border p-2"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
            />
          </label>
        </div>
        <label className="block text-sm">
          Email
          <input
            aria-label="Email"
            type="email"
            className="mt-1 w-full rounded border p-2"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        {!initial && (
          <label className="block text-sm">
            Password iniziale
            <input
              aria-label="Password iniziale"
              required
              type="password"
              className="mt-1 w-full rounded border p-2"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
        )}
        <label className="block text-sm">
          Ruolo
          <select
            aria-label="Ruolo"
            className="mt-1 w-full rounded border p-2"
            value={role}
            onChange={(e) => setRole(e.target.value)}
          >
            {roles.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex gap-2 text-sm">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          Utente attivo
        </label>
        {mutation.isError && (
          <p role="alert" className="text-destructive text-sm">
            {errorMessage(mutation.error)}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="rounded border px-3 py-2" onClick={onClose}>
            Annulla
          </button>
          <button
            className="bg-primary text-primary-foreground rounded px-3 py-2"
            disabled={mutation.isPending}
          >
            Salva
          </button>
        </div>
      </form>
    </div>
  );
}

function UsersPanel({ data }: { data: UsersPayload }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<UserRow | "new" | null>(null);
  const [message, setMessage] = useState("");
  const refresh = async () => {
    setEditing(null);
    setMessage("Operazione completata.");
    await queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
  };
  const action = useMutation({
    mutationFn: async ({
      user,
      kind,
    }: {
      user: UserRow;
      kind: "disable" | "password" | "delete";
    }) => {
      if (kind === "disable") return api.patch(`/admin/users/${user.id}`, { is_active: false });
      if (kind === "delete") return api.delete(`/admin/users/${user.id}`);
      const password = window.prompt(`Nuova password per ${user.username}`);
      if (!password) throw new Error("Operazione annullata.");
      return api.post(`/admin/users/${user.id}/password`, { password });
    },
    onSuccess: refresh,
  });
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Utenti</h2>
        <button
          className="bg-primary text-primary-foreground rounded px-3 py-2"
          onClick={() => setEditing("new")}
        >
          Crea utente
        </button>
      </div>
      {message && (
        <p role="status" className="text-sm text-emerald-700">
          {message}
        </p>
      )}
      {action.isError && (
        <p role="alert" className="text-destructive text-sm">
          {errorMessage(action.error)}
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b">
              <th className="p-2">Username</th>
              <th className="p-2">Nome</th>
              <th className="p-2">Email</th>
              <th className="p-2">Stato</th>
              <th className="p-2">Ruoli</th>
              <th className="p-2">Ultimo accesso</th>
              <th className="p-2">Creato</th>
              <th className="p-2">Azioni</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((user) => (
              <tr key={user.id} className="border-b">
                <td className="p-2 font-medium">{user.username}</td>
                <td className="p-2">
                  {user.first_name} {user.last_name}
                </td>
                <td className="p-2">{user.email}</td>
                <td className="p-2">
                  {user.is_active ? "Attivo" : "Disattivo"}
                  {user.is_staff ? " · staff" : ""}
                  {user.is_superuser ? " · superuser" : ""}
                </td>
                <td className="p-2">{user.roles.join(", ") || "—"}</td>
                <td className="p-2">
                  {user.last_login ? new Date(user.last_login).toLocaleString() : "Mai"}
                </td>
                <td className="p-2">{new Date(user.date_joined).toLocaleDateString()}</td>
                <td className="p-2">
                  <div className="flex flex-wrap gap-1">
                    <button className="rounded border px-2 py-1" onClick={() => setEditing(user)}>
                      Modifica
                    </button>
                    {user.is_active && (
                      <button
                        className="rounded border px-2 py-1"
                        onClick={() => {
                          if (window.confirm(`Disattivare ${user.username}?`))
                            action.mutate({ user, kind: "disable" });
                        }}
                      >
                        Disattiva
                      </button>
                    )}
                    <button
                      className="rounded border px-2 py-1"
                      onClick={() => action.mutate({ user, kind: "password" })}
                    >
                      Reset password
                    </button>
                    <button
                      className="border-destructive text-destructive rounded border px-2 py-1"
                      onClick={() => {
                        if (window.confirm(`Eliminare definitivamente ${user.username}?`))
                          action.mutate({ user, kind: "delete" });
                      }}
                    >
                      Elimina
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && (
        <UserForm
          roles={data.roles}
          initial={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
          onSaved={() => void refresh()}
        />
      )}
    </section>
  );
}

function RolesPanel({ data }: { data: RolesPayload }) {
  const queryClient = useQueryClient();
  const [matrix, setMatrix] = useState<Record<string, Set<string>>>(() =>
    Object.fromEntries(data.roles.map((role) => [role.key, new Set(role.capabilities)])),
  );
  const [message, setMessage] = useState("");
  const save = useMutation({
    mutationFn: (role: string) =>
      api.put("/admin/roles/capabilities", {
        role,
        capabilities: [...(matrix[role] ?? new Set<string>())],
      }),
    onSuccess: async () => {
      setMessage("Privilegi salvati.");
      await queryClient.invalidateQueries({ queryKey: ["admin", "roles"] });
    },
  });
  function toggle(role: string, capability: string) {
    setMatrix((current) => {
      const selected = new Set(current[role]);
      if (selected.has(capability)) selected.delete(capability);
      else selected.add(capability);
      return { ...current, [role]: selected };
    });
  }
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-medium">Ruoli e privilegi</h2>
      <p className="text-sm text-muted-foreground">
        Admin conserva tutte le capability. I privilegi riservati non sono assegnabili agli altri
        ruoli.
      </p>
      {message && (
        <p role="status" className="text-sm text-emerald-700">
          {message}
        </p>
      )}
      {save.isError && (
        <p role="alert" className="text-destructive text-sm">
          {errorMessage(save.error)}
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="p-2 text-left">Capability</th>
              {data.roles.map((role) => (
                <th key={role.key} className="p-2">
                  {role.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.capabilities.map((capability) => (
              <tr key={capability} className="border-t">
                <td className="p-2 font-mono">{capability}</td>
                {data.roles.map((role) => {
                  const locked = role.key === "admin" || data.reserved.includes(capability);
                  return (
                    <td key={role.key} className="p-2 text-center">
                      <input
                        aria-label={`${role.label}: ${capability}`}
                        type="checkbox"
                        checked={matrix[role.key]?.has(capability) ?? false}
                        disabled={locked}
                        onChange={() => toggle(role.key, capability)}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-2">
        {data.roles
          .filter((role) => role.key !== "admin")
          .map((role) => (
            <button
              key={role.key}
              className="bg-primary text-primary-foreground rounded px-3 py-2"
              onClick={() => save.mutate(role.key)}
            >
              Salva {role.label}
            </button>
          ))}
      </div>
    </section>
  );
}

export function AdminPage() {
  const [tab, setTab] = useState<Tab>("imports");
  const imports = useQuery({
    queryKey: ["admin", "imports"],
    queryFn: () => api.get<{ results: ImportRow[] }>("/admin/imports"),
  });
  const users = useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => api.get<UsersPayload>("/admin/users"),
  });
  const roleCapabilities = useQuery({
    queryKey: ["admin", "roles"],
    queryFn: () => api.get<RolesPayload>("/admin/roles/capabilities"),
  });
  if (imports.isLoading || users.isLoading || roleCapabilities.isLoading) return <LoadingState />;
  if (
    imports.isError ||
    users.isError ||
    roleCapabilities.isError ||
    !imports.data ||
    !users.data ||
    !roleCapabilities.data
  )
    return <ErrorState title="Amministrazione non disponibile" />;
  return (
    <section className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold">Amministrazione</h1>
        <p className="text-sm text-muted-foreground">Import, utenti, ruoli e privilegi.</p>
      </header>
      <nav aria-label="Sezioni amministrazione" className="flex gap-2 border-b">
        {(
          [
            ["imports", "Import ed export"],
            ["users", "Utenti"],
            ["roles", "Ruoli e privilegi"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            className={`border-b-2 px-3 py-2 ${tab === key ? "border-primary font-medium" : "border-transparent"}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </nav>
      {tab === "imports" && (
        <div className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-2">
            <ImportPanel kind="seed" title="Import seed JSON" accept="application/json,.json" />
            <ImportPanel kind="ppm" title="Import PPM" accept=".xlsx,.pdf" />
          </div>
          <section className="rounded-lg border p-4">
            <h2 className="mb-3 font-medium">Export</h2>
            <div className="flex gap-2">
              <a className="rounded border px-3 py-2" href={`${API_BASE}/export/json`}>
                JSON
              </a>
              <a className="rounded border px-3 py-2" href={`${API_BASE}/export/excel`}>
                Excel
              </a>
            </div>
            <h3 className="mb-2 mt-4 font-medium">Storico import</h3>
            {imports.data.results.length ? (
              <ul>
                {imports.data.results.map((row) => (
                  <li key={row.id}>
                    {row.kind} · {row.status} · {row.source_filename}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">Nessun import registrato.</p>
            )}
          </section>
        </div>
      )}
      {tab === "users" && <UsersPanel data={users.data} />}
      {tab === "roles" && <RolesPanel data={roleCapabilities.data} />}
    </section>
  );
}
