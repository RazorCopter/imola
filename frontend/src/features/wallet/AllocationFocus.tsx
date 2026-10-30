import { useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button, Input, Select } from "@/components/Controls";
import { DaysValue } from "@/components/DaysValue";
import { KpiCard } from "@/components/KpiCard";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState, LoadingState } from "@/components/UiState";
import { useSession } from "@/features/auth/session";
import { authorLabel, useTimesheetAuthors } from "@/features/timesheets/authors";
import { ApiError, api } from "@/lib/api";
import {
  canAssignTimesheetAuthor,
  canCreateTimesheets,
  canEditTimesheets,
} from "@/lib/permissions";
import { EditAllocationDialog } from "./EditAllocationDialog";
import type { Flow } from "./WalletPage";

interface AllocationTimesheet {
  id: string;
  data: string;
  giornate: string;
  descrizione: string;
  utente: string;
  utente_id: number | null;
  origine: string;
}
interface AllocationDetail {
  id: string;
  version: number;
  allocated_days: string;
  consumed_days: string;
  available_days: string;
  status: "APERTA" | "CHIUSA";
  stato_operativo: "IN_CORSO" | "CHIUSA";
  destinazione_titolo?: string;
  activity_code: string;
  activity_title: string;
  architetto: string | null;
  consuntivi: AllocationTimesheet[];
  funding: { progetto: string; residuo?: string }[];
}

const buttonClass =
  "rounded-md border border-input px-3 py-2 text-sm hover:bg-muted disabled:opacity-50";
const primaryButtonClass =
  "rounded-md bg-accent px-4 py-2 text-sm font-semibold uppercase tracking-wide text-accent-foreground hover:bg-accent/90 disabled:opacity-50";
const fieldClass = "h-9 w-full rounded-md border border-input bg-background px-3 text-sm";

function message(error: unknown): string {
  if (error instanceof ApiError) {
    const fields = Object.values(error.fieldErrors);
    if (fields.length) return fields.join(" ");
    return error.problem.detail || error.problem.title;
  }
  return error instanceof Error ? error.message : "Operazione non riuscita.";
}

const emptyForm = { data: "", giornate: "", descrizione: "", utente: "" };

/**
 * Vista operativa di una voce di wallet: la si apre per lavorarci, quindi resta in vista
 * lei sola, con i comandi in evidenza e i consuntivi che erodono le giornate riservate.
 */
export function AllocationFocus({
  allocation,
  year,
  canEdit,
  canAdjustConsumed,
  onBack,
  onChanged,
  onDeleted,
}: {
  allocation: Flow;
  year: number;
  canEdit: boolean;
  canAdjustConsumed: boolean;
  onBack: () => void;
  onChanged: () => Promise<void> | void;
  onDeleted: () => Promise<void>;
}) {
  const { session } = useSession();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("Consuntivi");
  const [form, setForm] = useState(emptyForm);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const canConsuntiva = canCreateTimesheets(session);
  const canEditConsuntivi = canEditTimesheets(session);
  const canChooseAuthor = canAssignTimesheetAuthor(session);
  const authors = useTimesheetAuthors(canChooseAuthor);

  // In sola lettura la stessa scheda vale come consultazione: cambia solo il nome.
  const detailTab = canEdit ? "Modifica" : "Dettaglio";

  const detail = useQuery({
    queryKey: ["wallet", "allocation", allocation.id],
    queryFn: () => api.get<AllocationDetail>(`/wallet/allocations/${allocation.id}`),
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["wallet", "allocation", allocation.id] });
    await onChanged();
  };

  const saveTimesheet = useMutation({
    mutationFn: () =>
      editingId
        ? api.patch(`/wallet/allocations/${allocation.id}/timesheets/${editingId}`, form)
        : api.post(`/wallet/allocations/${allocation.id}/timesheets`, form),
    onSuccess: async () => {
      setForm(emptyForm);
      setEditingId(null);
      setFormOpen(false);
      setError("");
      await refresh();
    },
    onError: (err) => setError(message(err)),
  });
  const removeTimesheet = useMutation({
    mutationFn: (entryId: string) =>
      api.delete(`/wallet/allocations/${allocation.id}/timesheets/${entryId}`),
    onSuccess: refresh,
    onError: (err) => setError(message(err)),
  });
  const closeAllocation = useMutation({
    mutationFn: () =>
      api.patch(`/wallet/allocations/${allocation.id}`, {
        status: "CHIUSA",
        expected_version: detail.data?.version ?? allocation.version,
      }),
    onSuccess: async () => {
      setError("");
      await refresh();
    },
    onError: (err) => setError(message(err)),
  });

  const consuntivi = detail.data?.consuntivi ?? [];
  const consumed = detail.data?.consumed_days ?? allocation.consumato;
  const allocated = detail.data?.allocated_days ?? allocation.allocato;
  const available = detail.data?.available_days ?? allocation.residuo_allocazione;
  const closed = (detail.data?.status ?? allocation.stato_operativo) === "CHIUSA";
  const percent =
    Number(allocated) > 0 ? Math.min(100, (Number(consumed) / Number(allocated)) * 100) : 0;

  function openForm() {
    setTab("Consuntivi");
    setEditingId(null);
    setForm({ ...emptyForm, data: new Date().toISOString().slice(0, 10) });
    setFormOpen(true);
    setError("");
  }

  return (
    <section className="space-y-4 rounded-lg border bg-card p-4" aria-label="Voce di wallet">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button type="button" className={buttonClass} onClick={onBack}>
          ← Tutte le allocazioni
        </Button>
        <div className="flex flex-wrap items-center gap-2">
          {canConsuntiva && !closed && (
            <Button type="button" className={primaryButtonClass} onClick={openForm}>
              CONSUNTIVA
            </Button>
          )}
          {canEdit && !closed && (
            <Button
              type="button"
              className={buttonClass}
              disabled={closeAllocation.isPending}
              onClick={() => closeAllocation.mutate()}
              title="Chiude la voce e restituisce al wallet le giornate riservate non usate"
            >
              Chiudi e rilascia
            </Button>
          )}
          {canEdit && (
            <Button type="button" className={buttonClass} onClick={() => setTab(detailTab)}>
              Modifica
            </Button>
          )}
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        Wallet {year} · origine {allocation.origine_titolo}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">{allocation.destinazione_titolo}</h2>
        <StatusBadge status={closed ? "CHIUSA" : "IN_CORSO"} />
        <span className="text-xs text-muted-foreground">{allocation.architetto ?? "—"}</span>
      </div>
      <div className="max-w-md">
        <span className="block h-1.5 overflow-hidden rounded-full bg-muted">
          <span
            className="block h-full rounded-full bg-primary"
            style={{ width: `${percent}%` }}
            aria-hidden
          />
        </span>
        <span className="mt-1 block text-xs text-muted-foreground">
          Consuntivate <DaysValue value={consumed} suffix={false} /> /{" "}
          <DaysValue value={allocated} />
        </span>
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <Tabs.Root value={tab} onValueChange={setTab}>
        <Tabs.List aria-label="Dettaglio allocazione" className="flex gap-4 border-b">
          {["Consuntivi", "Panoramica", detailTab].map((item) => (
            <Tabs.Trigger
              key={item}
              value={item}
              className="border-b-2 border-transparent px-2 py-2 text-sm data-[state=active]:border-primary data-[state=active]:font-semibold"
            >
              {item}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        <Tabs.Content value="Consuntivi" className="space-y-3 pt-4">
          {closed && (
            <p className="text-sm text-muted-foreground">
              Voce chiusa: le giornate riservate non usate sono state restituite al wallet.
            </p>
          )}
          {formOpen && (
            <div className="grid gap-2 rounded border border-dashed p-3 sm:grid-cols-4">
              <Input
                className={fieldClass}
                aria-label="Data consuntivo"
                type="date"
                value={form.data}
                onChange={(event) => setForm({ ...form, data: event.target.value })}
              />
              <Input
                className={fieldClass}
                aria-label="Giornate consuntivo"
                type="number"
                min="0.01"
                step="0.01"
                placeholder="Giornate"
                value={form.giornate}
                onChange={(event) => setForm({ ...form, giornate: event.target.value })}
              />
              <Input
                className={fieldClass}
                aria-label="Descrizione consuntivo"
                placeholder="Descrizione"
                value={form.descrizione}
                onChange={(event) => setForm({ ...form, descrizione: event.target.value })}
              />
              {canChooseAuthor && (
                <Select
                  className={fieldClass}
                  aria-label="Utente che consuntiva"
                  value={form.utente}
                  onChange={(event) => setForm({ ...form, utente: event.target.value })}
                >
                  <option value="">Io ({session?.username})</option>
                  {(authors.data?.results ?? []).map((author) => (
                    <option key={author.id} value={String(author.id)}>
                      {authorLabel(author)}
                    </option>
                  ))}
                </Select>
              )}
              <Button
                type="button"
                className={primaryButtonClass}
                disabled={saveTimesheet.isPending}
                onClick={() => saveTimesheet.mutate()}
              >
                {editingId ? "Salva rettifica" : "Registra"}
              </Button>
              <Button
                type="button"
                className={buttonClass}
                onClick={() => {
                  setFormOpen(false);
                  setEditingId(null);
                  setError("");
                }}
              >
                Annulla
              </Button>
            </div>
          )}
          {detail.isLoading ? (
            <LoadingState />
          ) : consuntivi.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th className="p-2">Data</th>
                    <th className="p-2">Utente</th>
                    <th className="p-2 text-right">Giornate</th>
                    <th className="p-2">Descrizione</th>
                    {canEditConsuntivi && <th className="p-2">Azioni</th>}
                  </tr>
                </thead>
                <tbody>
                  {consuntivi.map((entry) => (
                    <tr key={entry.id} className="border-b">
                      <td className="p-2">{entry.data}</td>
                      <td className="p-2">{entry.utente}</td>
                      <td className="p-2 text-right">
                        <DaysValue value={entry.giornate} />
                      </td>
                      <td className="p-2">{entry.descrizione}</td>
                      {canEditConsuntivi && (
                        <td className="flex gap-2 p-2">
                          <Button
                            type="button"
                            className={buttonClass}
                            onClick={() => {
                              setEditingId(entry.id);
                              setForm({
                                data: entry.data,
                                giornate: entry.giornate,
                                descrizione: entry.descrizione,
                                utente: entry.utente_id ? String(entry.utente_id) : "",
                              });
                              setFormOpen(true);
                              setError("");
                            }}
                          >
                            Modifica
                          </Button>
                          <Button
                            type="button"
                            className={buttonClass}
                            disabled={removeTimesheet.isPending}
                            onClick={() => {
                              if (window.confirm(`Eliminare il consuntivo del ${entry.data}?`)) {
                                removeTimesheet.mutate(entry.id);
                              }
                            }}
                          >
                            Elimina
                          </Button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="Nessun consuntivo registrato" />
          )}
        </Tabs.Content>

        <Tabs.Content value="Panoramica" className="space-y-3 pt-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <KpiCard label="Riservato" value={<DaysValue value={allocated} />} />
            <KpiCard label="Consuntivato" value={<DaysValue value={consumed} />} />
            <KpiCard label="Residuo" value={<DaysValue value={available} />} tone="ok" />
          </div>
          <p className="text-sm text-muted-foreground">
            Origine: {allocation.origine_titolo}
            {allocation.scadenza_origine ? ` · scade ${allocation.scadenza_origine}` : ""}
          </p>
        </Tabs.Content>

        <Tabs.Content value={detailTab} className="pt-4">
          <EditAllocationDialog
            allocationId={allocation.id}
            year={year}
            canEdit={canEdit}
            canAdjustConsumed={canAdjustConsumed}
            onSaved={refresh}
            onDeleted={onDeleted}
          />
        </Tabs.Content>
      </Tabs.Root>
    </section>
  );
}
