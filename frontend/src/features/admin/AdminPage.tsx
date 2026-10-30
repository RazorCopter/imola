import { useDialogFocusReturn } from "@/lib/useDialogFocusReturn";
import { PageHeader } from "@/components/PageHeader";
import { Button, Input, Select } from "@/components/Controls";
import { FormEvent, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/UiState";
import { API_BASE, ApiError, api } from "@/lib/api";
import { useSession } from "@/features/auth/session";
import { TIMESHEET_AUTHORS_KEY } from "@/features/timesheets/authors";
import { canResetData } from "@/lib/permissions";
import { DeleteDatabaseDialog } from "./DeleteDatabaseDialog";

interface Preview {
  mode: string;
  confirmation_hash: string;
  batch_id?: string | null;
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
  report?: Record<string, unknown>;
}
interface WorkbookDatasetSummary {
  id: string;
  dataset_id: string;
  sheet: string;
  range: string;
  row_count: number;
  column_count: number;
  columns: { key: string; label: string | number | null }[];
}
interface WorkbookDatasetDetail extends WorkbookDatasetSummary {
  rows: { source_row: number; values: Record<string, unknown> }[];
}
interface AppSettingsPayload {
  costo_forfettario_canone: string;
  costo_giornata_uomo: string;
  politica_costo: string;
  version: number;
}
interface ReferentRow {
  id: string;
  full_name: string;
  email: string | null;
  is_active: boolean;
  organization_kind: "CLIENT" | "SUPPLIER";
  organization_label: string;
  project_count: number;
}
type Tab = "imports" | "users" | "referents" | "roles" | "configuration";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const fields = Object.values(error.fieldErrors);
    return fields.length ? fields.join(" ") : error.message;
  }
  return error instanceof Error ? error.message : "Operazione non riuscita.";
}

function DatabaseBackupPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const restore = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Seleziona un backup.");
      const form = new FormData();
      form.append("file", file);
      form.append("confirm", confirmation);
      return api.post<{ detail: string; backup_preventivo: string }>(
        "/admin/database/restore",
        form,
      );
    },
  });
  return (
    <section className="space-y-3 rounded-lg border p-4">
      <h2 className="font-medium">Backup e ripristino database</h2>
      <p className="text-sm text-muted-foreground">
        Il backup contiene il database completo, inclusi utenti e configurazione. Gli allegati e i
        file media non sono inclusi.
      </p>
      <a
        className="inline-block rounded border px-3 py-2 text-sm"
        href={`${API_BASE}/admin/database/backup`}
      >
        Scarica backup database
      </a>
      <div className="space-y-2 border-t pt-3">
        <h3 className="font-medium">Ripristina database</h3>
        <p className="text-sm text-muted-foreground">
          Il ripristino accetta file fino a 28 MB e sostituisce i dati attuali. Viene creata una
          copia preventiva sul server. Durante il ripristino sospendi le altre operazioni; potrebbe
          essere necessario accedere di nuovo.
        </p>
        <Input
          aria-label="File backup database"
          disabled={restore.isPending}
          type="file"
          accept=".dump"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            setConfirmation("");
            restore.reset();
          }}
        />
        <label className="block text-sm">
          Scrivi RIPRISTINA per confermare{" "}
          <Input
            className="ml-2 rounded border bg-background px-2 py-1"
            value={confirmation}
            disabled={restore.isPending}
            onChange={(e) => setConfirmation(e.target.value)}
          />
        </label>
        <Button
          className="rounded bg-red-700 px-3 py-2 text-sm text-white disabled:opacity-50"
          disabled={!file || confirmation !== "RIPRISTINA" || restore.isPending}
          onClick={() => restore.mutate()}
        >
          Ripristina database
        </Button>
        {restore.isError && (
          <p role="alert" className="text-sm text-destructive">
            {errorMessage(restore.error)}
          </p>
        )}
        {restore.data && (
          <p role="status" className="text-sm">
            {restore.data.detail} Copia preventiva: {restore.data.backup_preventivo}
          </p>
        )}
      </div>
    </section>
  );
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
  const report = preview?.report as
    | {
        schema_version?: string;
        esito?: string;
        riepilogo?: Record<string, number>;
        totali_calcolati?: Record<string, unknown>;
      }
    | undefined;
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
    <section className="rounded-xl border border-border bg-card p-5 shadow-subtle">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Selezione · Simulazione · Conferma
      </p>
      <h2 className="font-semibold tracking-tight">{title}</h2>
      <Input
        aria-label={`File per ${title}`}
        className="mt-4 block w-full rounded-md border border-input bg-background p-2 text-sm file:mr-3 file:rounded file:border-0 file:bg-muted file:px-3 file:py-1 file:text-foreground"
        type="file"
        accept={accept}
        disabled={upload.isPending}
        onChange={(e) => {
          setFile(e.target.files?.[0] ?? null);
          setPreview(null);
          upload.reset();
        }}
      />
      <div className="mt-3 flex gap-2">
        <Button
          className="rounded border px-3 py-2 text-sm"
          disabled={!file || upload.isPending}
          onClick={() => upload.mutate(false)}
        >
          Valida e simula
        </Button>
        <Button
          className="rounded border border-emerald-800 bg-emerald-700 px-3 py-2 text-sm text-white disabled:opacity-50"
          disabled={!file || !hasValidPreview || upload.isPending}
          onClick={() => upload.mutate(true)}
        >
          Conferma e applica
        </Button>
      </div>
      {!hasValidPreview && (
        <p className="mt-2 text-xs text-muted-foreground">Esegui prima “Valida e simula”.</p>
      )}
      {upload.isError && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {errorMessage(upload.error)}
        </p>
      )}
      {preview && (
        <div className="mt-3 space-y-2 rounded bg-muted p-3 text-xs">
          <p role="status" className="font-medium">
            Schema {report?.schema_version ?? "non indicato"} · {report?.esito ?? "elaborato"}
          </p>
          {report?.riepilogo && (
            <p>
              Creati {report.riepilogo.creati ?? 0} · aggiornati {report.riepilogo.aggiornati ?? 0}{" "}
              · scartati {report.riepilogo.scartati ?? 0} · errori {report.riepilogo.errori ?? 0}
            </p>
          )}
          {report?.totali_calcolati && (
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
              {Object.entries(report.totali_calcolati).map(([key, value]) => (
                <div key={key} className="contents">
                  <dt className="text-muted-foreground">{key.replaceAll("_", " ")}</dt>
                  <dd className="text-right font-medium">{String(value)}</dd>
                </div>
              ))}
            </dl>
          )}
          <details>
            <summary className="cursor-pointer">Report tecnico completo</summary>
            <pre className="mt-2 max-h-64 overflow-auto">
              {JSON.stringify(preview.report, null, 2)}
            </pre>
          </details>
        </div>
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
  const dialogFocus = useDialogFocusReturn();
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
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content
          {...dialogFocus}
          className="fixed left-1/2 top-1/2 z-50 max-h-[90dvh] w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border border-border bg-card p-5 shadow-raised"
        >
          <form onSubmit={submit} className="space-y-3">
            <Dialog.Title className="text-lg font-semibold">
              {initial ? "Modifica utente" : "Crea utente"}
            </Dialog.Title>
            <Dialog.Description className="text-sm text-muted-foreground">
              Dati account, ruolo e stato di accesso.
            </Dialog.Description>
            <label className="block text-sm">
              Username
              <Input
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
                <Input
                  aria-label="Nome"
                  className="mt-1 w-full rounded border p-2"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                />
              </label>
              <label className="text-sm">
                Cognome
                <Input
                  aria-label="Cognome"
                  className="mt-1 w-full rounded border p-2"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                />
              </label>
            </div>
            <label className="block text-sm">
              Email
              <Input
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
                <Input
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
              <Select
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
              </Select>
            </label>
            <label className="flex gap-2 text-sm">
              <Input
                type="checkbox"
                checked={active}
                onChange={(e) => setActive(e.target.checked)}
              />
              Utente attivo
            </label>
            {mutation.isError && (
              <p role="alert" className="text-sm text-destructive">
                {errorMessage(mutation.error)}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button type="button" className="rounded border px-3 py-2" onClick={onClose}>
                Annulla
              </Button>
              <Button
                className="rounded bg-primary px-3 py-2 text-primary-foreground"
                disabled={mutation.isPending}
              >
                Salva
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function UsersPanel({ data }: { data: UsersPayload }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<UserRow | "new" | null>(null);
  const [message, setMessage] = useState("");
  const refresh = async () => {
    setEditing(null);
    setMessage("Operazione completata.");
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] }),
      // Un utente nuovo (o un ruolo cambiato) muove anche gli autori proponibili
      // nei form di consuntivazione.
      queryClient.invalidateQueries({ queryKey: TIMESHEET_AUTHORS_KEY }),
    ]);
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
        <Button
          className="rounded bg-primary px-3 py-2 text-primary-foreground"
          onClick={() => setEditing("new")}
        >
          Crea utente
        </Button>
      </div>
      {message && (
        <p role="status" className="text-sm text-ok">
          {message}
        </p>
      )}
      {action.isError && (
        <p role="alert" className="text-sm text-destructive">
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
                    <Button className="rounded border px-2 py-1" onClick={() => setEditing(user)}>
                      Modifica
                    </Button>
                    {user.is_active && (
                      <Button
                        className="rounded border px-2 py-1"
                        onClick={() => {
                          if (window.confirm(`Disattivare ${user.username}?`))
                            action.mutate({ user, kind: "disable" });
                        }}
                      >
                        Disattiva
                      </Button>
                    )}
                    <Button
                      className="rounded border px-2 py-1"
                      onClick={() => action.mutate({ user, kind: "password" })}
                    >
                      Reset password
                    </Button>
                    <Button
                      className="rounded border border-destructive px-2 py-1 text-destructive"
                      onClick={() => {
                        if (window.confirm(`Eliminare definitivamente ${user.username}?`))
                          action.mutate({ user, kind: "delete" });
                      }}
                    >
                      Elimina
                    </Button>
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

function ConfigurationPanel() {
  const queryClient = useQueryClient();
  const [cost, setCost] = useState<string | null>(null);
  const [canoneCost, setCanoneCost] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<AppSettingsPayload>("/settings"),
  });
  const save = useMutation({
    mutationFn: () =>
      api.patch<AppSettingsPayload>("/settings", {
        costo_giornata_uomo: cost ?? settings.data?.costo_giornata_uomo,
        costo_forfettario_canone: canoneCost ?? settings.data?.costo_forfettario_canone ?? "0.00",
        expected_version: settings.data?.version,
      }),
    onSuccess: async (result) => {
      setCost(result.costo_giornata_uomo);
      setCanoneCost(result.costo_forfettario_canone);
      setMessage("Configurazione salvata.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["settings"] }),
        queryClient.invalidateQueries({ queryKey: ["cost-analysis"] }),
      ]);
    },
  });
  const shownCost = cost ?? settings.data?.costo_giornata_uomo ?? "";
  const shownCanoneCost = canoneCost ?? settings.data?.costo_forfettario_canone ?? "0.00";
  const valid = [shownCost, shownCanoneCost].every(
    (value) => value !== "" && Number.isFinite(Number(value)) && Number(value) >= 0,
  );
  if (settings.isLoading) return <LoadingState />;
  if (settings.isError)
    return (
      <ErrorState title="Configurazione non disponibile" detail={errorMessage(settings.error)} />
    );
  return (
    <section className="max-w-xl space-y-4 rounded-lg border border-border bg-card p-4">
      <h2 className="text-lg font-medium">Configurazione costi</h2>
      <p className="text-sm text-muted-foreground">{settings.data?.politica_costo}</p>
      <label className="block text-sm font-medium" htmlFor="daily-person-cost">
        Costo giornata uomo (€)
      </label>
      <Input
        id="daily-person-cost"
        type="number"
        min="0"
        step="0.01"
        value={shownCost}
        onChange={(event) => {
          setCost(event.target.value);
          setMessage("");
        }}
        className="w-full rounded-md border border-input bg-background px-3 py-2"
      />
      <label className="block text-sm font-medium" htmlFor="canone-fixed-cost">
        Costo forfettario per canone (EUR)
      </label>
      <Input
        id="canone-fixed-cost"
        type="number"
        min="0"
        step="0.01"
        value={shownCanoneCost}
        onChange={(event) => {
          setCanoneCost(event.target.value);
          setMessage("");
        }}
        aria-describedby="canone-fixed-cost-help"
        className="w-full rounded-md border border-input bg-background px-3 py-2"
      />
      <p id="canone-fixed-cost-help" className="text-sm text-muted-foreground">
        Importo intero pagato all'attivazione di ciascun canone di Organico Allargato, indipendente
        dalle giornate previste e consuntivate. Valore corrente, non storicizzato.
      </p>
      {!valid && <p className="text-sm text-destructive">Inserire un importo non negativo.</p>}
      {message && (
        <p role="status" className="text-sm text-ok">
          {message}
        </p>
      )}
      {save.isError && (
        <p role="alert" className="text-sm text-destructive">
          {errorMessage(save.error)}
        </p>
      )}
      <Button
        type="button"
        disabled={!valid || save.isPending}
        onClick={() => save.mutate()}
        className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
      >
        {save.isPending ? "Salvataggio…" : "Salva"}
      </Button>
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
        <p role="status" className="text-sm text-ok">
          {message}
        </p>
      )}
      {save.isError && (
        <p role="alert" className="text-sm text-destructive">
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
                      <Input
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
            <Button
              key={role.key}
              className="rounded bg-primary px-3 py-2 text-primary-foreground"
              onClick={() => save.mutate(role.key)}
            >
              Salva {role.label}
            </Button>
          ))}
      </div>
    </section>
  );
}

function WorkbookExplorer({ batch, onClose }: { batch: ImportRow; onClose: () => void }) {
  const [datasetId, setDatasetId] = useState("");
  const datasets = useQuery({
    queryKey: ["admin", "workbook-datasets", batch.id],
    queryFn: () =>
      api.get<{ results: WorkbookDatasetSummary[] }>(`/admin/imports/${batch.id}/datasets`),
  });
  const selected = datasets.data?.results.find((dataset) => dataset.id === datasetId);
  const detail = useQuery({
    queryKey: ["admin", "workbook-dataset", batch.id, datasetId],
    queryFn: () =>
      api.get<WorkbookDatasetDetail>(`/admin/imports/${batch.id}/datasets/${datasetId}`),
    enabled: Boolean(datasetId),
  });
  return (
    <section className="space-y-3 rounded-lg border border-primary/30 bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-medium">Dataset di {batch.source_filename}</h3>
          <p className="text-xs text-muted-foreground">Batch {batch.id}</p>
        </div>
        <Button className="rounded border px-2 py-1 text-sm" onClick={onClose}>
          Chiudi
        </Button>
      </div>
      {datasets.isLoading && <LoadingState />}
      {datasets.isError && <ErrorState title="Dataset non disponibili" />}
      {datasets.data && (
        <Select
          aria-label="Dataset workbook"
          className="w-full rounded border bg-background p-2 text-sm"
          value={datasetId}
          onChange={(event) => setDatasetId(event.target.value)}
        >
          <option value="">Seleziona un dataset</option>
          {datasets.data.results.map((dataset) => (
            <option key={dataset.id} value={dataset.id}>
              {dataset.dataset_id} ({dataset.row_count} righe)
            </option>
          ))}
        </Select>
      )}
      {selected && detail.data && (
        <div className="max-h-[32rem] overflow-auto rounded border">
          <table className="min-w-full whitespace-nowrap text-left text-xs">
            <thead className="sticky top-0 bg-muted">
              <tr>
                <th className="p-2">Riga</th>
                {selected.columns.map((column) => (
                  <th key={column.key} className="p-2">
                    {String(column.label ?? column.key)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {detail.data.rows.map((row) => (
                <tr key={row.source_row} className="border-t">
                  <td className="p-2 font-mono">{row.source_row}</td>
                  {selected.columns.map((column) => {
                    const rawValue = row.values[column.key];
                    let value = "";
                    if (rawValue !== null && rawValue !== undefined) {
                      if (typeof rawValue === "string") {
                        value = rawValue;
                      } else if (typeof rawValue === "number" || typeof rawValue === "boolean") {
                        value = String(rawValue);
                      } else {
                        value = JSON.stringify(rawValue);
                      }
                    }
                    return (
                      <td
                        key={column.key}
                        className="max-w-72 overflow-hidden text-ellipsis p-2"
                        title={value}
                      >
                        {value}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function ReferentsPanel() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<ReferentRow | null>(null);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [organizationKind, setOrganizationKind] = useState<"CLIENT" | "SUPPLIER">("CLIENT");
  const referents = useQuery({
    queryKey: ["admin", "referents"],
    queryFn: () => api.get<{ results: ReferentRow[] }>("/admin/referents"),
  });
  const save = useMutation({
    mutationFn: () => {
      const payload = {
        full_name: fullName,
        email,
        organization_kind: organizationKind,
      };
      return editing
        ? api.patch(`/admin/referents/${editing.id}`, payload)
        : api.post("/admin/referents", payload);
    },
    onSuccess: async () => {
      setEditing(null);
      setFullName("");
      setEmail("");
      setOrganizationKind("CLIENT");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin", "referents"] }),
        queryClient.invalidateQueries({ queryKey: ["project-options"] }),
      ]);
    },
  });
  const setActive = useMutation({
    mutationFn: ({ row, active }: { row: ReferentRow; active: boolean }) =>
      active
        ? api.patch(`/admin/referents/${row.id}`, { is_active: true })
        : api.delete(`/admin/referents/${row.id}`),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin", "referents"] }),
        queryClient.invalidateQueries({ queryKey: ["project-options"] }),
      ]);
    },
  });

  if (referents.isLoading) return <LoadingState />;
  if (referents.isError || !referents.data)
    return <ErrorState title="Impossibile caricare i referenti" />;

  return (
    <div className="space-y-4">
      <form
        className="grid gap-3 rounded-lg border border-border bg-card p-4 md:grid-cols-[1fr_1fr_14rem_auto] md:items-end"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <label className="text-sm">
          Nome e cognome
          <Input
            required
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            className="mt-1 w-full rounded border border-input bg-background px-3 py-2"
          />
        </label>
        <label className="text-sm">
          Email
          <Input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-1 w-full rounded border border-input bg-background px-3 py-2"
          />
        </label>
        <label className="text-sm">
          Tipologia
          <Select
            value={organizationKind}
            onChange={(event) => setOrganizationKind(event.target.value as "CLIENT" | "SUPPLIER")}
            className="mt-1 w-full rounded border border-input bg-background px-3 py-2"
          >
            <option value="CLIENT">Collega BMED</option>
            <option value="SUPPLIER">Consulente Imola</option>
          </Select>
        </label>
        <div className="flex gap-2">
          <Button
            type="submit"
            disabled={save.isPending}
            className="rounded bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
          >
            {editing ? "Aggiorna" : "Aggiungi"}
          </Button>
          {editing && (
            <Button
              type="button"
              className="rounded border px-3 py-2 text-sm"
              onClick={() => {
                setEditing(null);
                setFullName("");
                setEmail("");
              }}
            >
              Annulla
            </Button>
          )}
        </div>
      </form>
      {save.isError && <p className="text-sm text-destructive">{errorMessage(save.error)}</p>}
      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left">
            <tr>
              <th className="p-3">Nome</th>
              <th className="p-3">Tipologia</th>
              <th className="p-3">Email</th>
              <th className="p-3 text-right">Progetti</th>
              <th className="p-3">Stato</th>
              <th className="p-3 text-right">Azioni</th>
            </tr>
          </thead>
          <tbody>
            {referents.data.results.map((row) => (
              <tr key={row.id} className="border-t border-border">
                <td className="p-3 font-medium">{row.full_name}</td>
                <td className="p-3">{row.organization_label}</td>
                <td className="p-3">{row.email || "—"}</td>
                <td className="p-3 text-right">{row.project_count}</td>
                <td className="p-3">{row.is_active ? "Attivo" : "Disattivato"}</td>
                <td className="p-3">
                  <div className="flex justify-end gap-2">
                    <Button
                      type="button"
                      className="rounded border px-2 py-1 text-xs"
                      onClick={() => {
                        setEditing(row);
                        setFullName(row.full_name);
                        setEmail(row.email ?? "");
                        setOrganizationKind(row.organization_kind);
                      }}
                    >
                      Modifica
                    </Button>
                    <Button
                      type="button"
                      className="rounded border px-2 py-1 text-xs"
                      disabled={setActive.isPending}
                      onClick={() => setActive.mutate({ row, active: !row.is_active })}
                    >
                      {row.is_active ? "Disattiva" : "Riattiva"}
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function AdminPage() {
  const [tab, setTab] = useState<Tab>("imports");
  const [showDeleteDbDialog, setShowDeleteDbDialog] = useState(false);
  const [workbookBatch, setWorkbookBatch] = useState<ImportRow | null>(null);
  const { session } = useSession();
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
      <PageHeader
        eyebrow="Sistema · Configurazione"
        title="Amministrazione"
        description="Import, utenti, referenti, ruoli e configurazione."
      />
      <div
        role="tablist"
        aria-label="Sezioni amministrazione"
        className="flex gap-2 overflow-x-auto border-b"
      >
        {(
          [
            ["imports", "Import ed export"],
            ["users", "Utenti"],
            ["referents", "Referenti"],
            ["roles", "Ruoli e privilegi"],
            ["configuration", "Configurazione"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <Button
            key={key}
            role="tab"
            id={`admin-tab-${key}`}
            aria-controls="admin-panel"
            tabIndex={tab === key ? 0 : -1}
            aria-selected={tab === key}
            className={`border-b-2 px-3 py-2 ${tab === key ? "border-primary font-medium" : "border-transparent"}`}
            onClick={() => setTab(key)}
            onKeyDown={(event) => {
              const keys: Tab[] = ["imports", "users", "referents", "roles", "configuration"];
              let next = keys.indexOf(key);
              if (event.key === "ArrowRight") next = (next + 1) % keys.length;
              else if (event.key === "ArrowLeft") next = (next + keys.length - 1) % keys.length;
              else if (event.key === "Home") next = 0;
              else if (event.key === "End") next = keys.length - 1;
              else return;
              event.preventDefault();
              setTab(keys[next]!);
              document.getElementById(`admin-tab-${keys[next]}`)?.focus();
            }}
          >
            {label}
          </Button>
        ))}
      </div>
      <div
        role="tabpanel"
        id="admin-panel"
        aria-labelledby={`admin-tab-${tab}`}
        className="space-y-4"
      >
        {tab === "imports" && (
          <div className="space-y-4">
            <div className="grid gap-4 xl:grid-cols-2">
              <ImportPanel
                kind="seed"
                title="Import JSON (seed v1 o workbook v2-v4)"
                accept="application/json,.json"
              />
              <ImportPanel kind="ppm" title="Import PPM" accept=".xlsx,.pdf" />
            </div>
            {session?.is_admin && <DatabaseBackupPanel />}
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
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b text-xs text-muted-foreground">
                      <tr>
                        <th className="p-3">File</th>
                        <th className="p-3">Tipo</th>
                        <th className="p-3">Stato</th>
                        <th className="p-3">Azione</th>
                      </tr>
                    </thead>
                    <tbody>
                      {imports.data.results.map((row) => (
                        <tr key={row.id} className="border-b last:border-0">
                          <td className="max-w-sm break-words p-3 font-medium">
                            {row.source_filename}
                          </td>
                          <td className="p-3">{row.kind}</td>
                          <td className="p-3">{row.status}</td>
                          <td className="p-3">
                            {row.kind === "WORKBOOK_JSON" && row.status === "APPLIED" && (
                              <Button
                                className="rounded border px-2 py-1 text-xs"
                                onClick={() => setWorkbookBatch(row)}
                              >
                                Esplora dataset
                              </Button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Nessun import registrato.</p>
              )}
            </section>
            {workbookBatch && (
              <WorkbookExplorer batch={workbookBatch} onClose={() => setWorkbookBatch(null)} />
            )}
          </div>
        )}
        {tab === "users" && <UsersPanel data={users.data} />}
        {tab === "referents" && <ReferentsPanel />}
        {tab === "roles" && <RolesPanel data={roleCapabilities.data} />}
        {tab === "configuration" && <ConfigurationPanel />}

        {tab === "configuration" && canResetData(session) && (
          <section className="mt-8 rounded-lg border-2 border-danger/40 bg-danger/5 p-4">
            <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
              <div>
                <h2 className="flex items-center gap-2 text-sm font-bold text-danger">
                  <AlertTriangle className="h-5 w-5" /> Attenzione - Reset Completo DB
                </h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  Cancellazione irreversibile di tutti i dati operativi (progetti, consuntivi,
                  wallet, canoni, anomalie, import). Gli utenti e le impostazioni restano intatti.
                  Richiede digitazione obbligatoria di conferma.
                </p>
              </div>
              <Button
                type="button"
                onClick={() => setShowDeleteDbDialog(true)}
                data-testid="open-delete-db-dialog-btn"
                className="inline-flex shrink-0 items-center justify-center rounded-md border-2 border-danger-action bg-danger-action px-4 py-2 text-xs font-bold uppercase tracking-wider text-white shadow-sm transition hover:bg-danger-action/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-danger"
              >
                ELIMINA DB
              </Button>
            </div>
          </section>
        )}
      </div>
      <DeleteDatabaseDialog
        open={showDeleteDbDialog}
        onClose={() => setShowDeleteDbDialog(false)}
      />
    </section>
  );
}
