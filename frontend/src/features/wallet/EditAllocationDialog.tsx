import { Button, Input, Select, Textarea } from "@/components/Controls";
import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Lock, RefreshCw, Trash2 } from "lucide-react";

import { DaysValue } from "@/components/DaysValue";
import { api, ApiError } from "@/lib/api";

export interface WalletAllocationDetail {
  id: string;
  version: number;
  external_ref: string | null;
  allocated_days: string;
  initial_allocated_days?: string;
  consumed_days: string;
  available_days: string;
  residuo_allocazione: string;
  residuo_spendibile_origine: string | null;
  validita_origine: string | null;
  scadenza_origine: string | null;
  status: string;
  closure_reason?: string | null;
  stato_operativo: string;
  notes: string;
  assignee: string | null;
  architetto: string | null;
  source_project_code: string | null;
  source_project_title: string | null;
  activity_code: string;
  activity_title: string;
  year: number;
  funding?: {
    ordine: number;
    progetto_origine: string;
    anno_provenienza: number;
    riservato_iniziale: string;
    impegnato: string;
    consumato: string;
  }[];
}
interface AllocationOptions {
  assignees: { id: string; name: string; full_name?: string }[];
  architects?: { id: string; name: string; full_name?: string }[];
}
interface Props {
  allocationId: string | null;
  year: number;
  canEdit: boolean;
  canAdjustConsumed: boolean;
  onSaved: () => Promise<void>;
  onDeleted: () => Promise<void>;
}

export function EditAllocationDialog({
  allocationId,
  year,
  canEdit,
  canAdjustConsumed,
  onSaved,
  onDeleted,
}: Props) {
  const queryClient = useQueryClient();
  const [allocatedDays, setAllocatedDays] = useState("");
  const [consumedDays, setConsumedDays] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const [status, setStatus] = useState("APERTA");
  const [notes, setNotes] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteCode, setDeleteCode] = useState("");

  const allocation = useQuery({
    queryKey: ["wallet", "allocation", allocationId],
    queryFn: () => api.get<WalletAllocationDetail>(`/wallet/allocations/${allocationId}/`),
    enabled: Boolean(allocationId),
  });
  const options = useQuery({
    queryKey: ["wallet", "allocation-options"],
    queryFn: () => api.get<AllocationOptions>("/wallet/allocation-options/"),
    enabled: Boolean(allocationId) && canEdit,
  });
  const detail = allocation.data;

  useEffect(() => {
    if (!detail) return;
    setAllocatedDays(detail.allocated_days);
    setConsumedDays(detail.consumed_days);
    setAssigneeId(detail.assignee ?? "");
    setStatus(detail.status);
    setNotes(detail.notes ?? "");
    setFormError(null);
    setConflict(false);
  }, [detail]);

  const save = useMutation({
    mutationFn: async () => {
      if (!detail || !allocationId) return;
      const numericDays = Number(allocatedDays);
      const numericConsumedDays = Number(consumedDays);
      if (!allocatedDays.trim() || !Number.isFinite(numericDays) || numericDays < 0) {
        throw new Error("Le giornate allocate devono essere un numero non negativo.");
      }
      if (
        !consumedDays.trim() ||
        !Number.isFinite(numericConsumedDays) ||
        numericConsumedDays < 0
      ) {
        throw new Error("Le giornate consumate devono essere un numero non negativo.");
      }
      if (numericConsumedDays > numericDays) {
        throw new Error("Le giornate consumate non possono superare quelle allocate.");
      }
      const consumedChanged = numericConsumedDays !== Number(detail.consumed_days);
      return api.patch<WalletAllocationDetail>(
        `/wallet/allocations/${allocationId}/`,
        {
          expected_version: detail.version,
          allocated_days: allocatedDays.trim(),
          ...(consumedChanged && canAdjustConsumed
            ? { adjust_consumed_to: consumedDays.trim() }
            : {}),
          assignee: assigneeId || null,
          status,
          notes: notes.trim(),
        },
        { headers: { "If-Match": `"${detail.version}"` } },
      );
    },
    onSuccess: async () => {
      await onSaved();
      await queryClient.invalidateQueries({ queryKey: ["wallet", "allocation", allocationId] });
    },
    onError: (error: unknown) => {
      setConflict(error instanceof ApiError && (error.status === 409 || error.status === 428));
      if (error instanceof ApiError) {
        const fields = error.problem.errors
          ?.map((item) => `${item.campo}: ${item.messaggio}`)
          .join("; ");
        setFormError(fields || error.problem.detail || error.message);
      } else {
        setFormError(error instanceof Error ? error.message : "Errore durante il salvataggio.");
      }
    },
  });

  const remove = useMutation({
    mutationFn: async () => {
      if (!detail || !allocationId) return;
      return api.delete<void>(`/wallet/allocations/${allocationId}/`, {
        ifMatch: `W/"${detail.id}-${detail.version}"`,
      });
    },
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: ["wallet", "allocation", allocationId] });
      setDeleteOpen(false);
      await onDeleted();
    },
    onError: (error: unknown) => {
      if (error instanceof ApiError) {
        setFormError(error.problem.detail || error.problem.title);
      } else {
        setFormError("Errore di rete durante l'eliminazione.");
      }
      setDeleteOpen(false);
    },
  });

  if (!allocationId) {
    return (
      <aside className="rounded-lg border bg-card p-5" aria-label="Dettaglio allocazione">
        <h2 className="font-medium">Dettaglio allocazione</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Seleziona una riga della lista per consultare dati e residui.
        </p>
      </aside>
    );
  }
  if (allocation.isLoading)
    return <aside className="rounded-lg border bg-card p-5">Caricamento dettaglio…</aside>;
  if (!detail)
    return (
      <aside className="rounded-lg border bg-card p-5 text-destructive">
        Impossibile caricare il dettaglio.
      </aside>
    );

  const architects = options.data?.architects ?? options.data?.assignees ?? [];
  const validity = (detail.validita_origine ?? "Non applicabile").replaceAll("_", " ");

  return (
    <aside className="rounded-lg border bg-card p-5" aria-label="Dettaglio allocazione">
      <div className="border-b pb-3">
        <h2 className="font-medium">Dettaglio allocazione</h2>
        <p className="font-mono text-xs text-muted-foreground">
          {detail.source_project_code ?? "WALLET-GENERALE"} → {detail.activity_code}
        </p>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 rounded bg-muted/40 p-3 text-sm">
        <div>
          <span className="block text-xs text-muted-foreground">Allocato</span>
          <DaysValue value={detail.allocated_days} />
        </div>
        <div>
          <span className="block text-xs text-muted-foreground">Consumato</span>
          <DaysValue value={detail.consumed_days} />
        </div>
        <div>
          <span className="block text-xs text-muted-foreground">Residuo allocazione</span>
          <DaysValue value={detail.residuo_allocazione ?? detail.available_days} />
        </div>
        <div>
          <span className="block text-xs text-muted-foreground">Residuo spendibile origine</span>
          {detail.residuo_spendibile_origine === null ? (
            "—"
          ) : (
            <DaysValue value={detail.residuo_spendibile_origine} />
          )}
        </div>
      </div>
      <div className="mt-3 rounded border p-3 text-sm">
        <span className="block text-xs text-muted-foreground">Validità residuo origine</span>
        <strong className="capitalize">{validity.toLocaleLowerCase()}</strong>
        {detail.scadenza_origine && (
          <span className="ml-2 text-xs text-muted-foreground">
            fino al {new Date(`${detail.scadenza_origine}T00:00:00`).toLocaleDateString("it-IT")}
          </span>
        )}
      </div>
      {detail.funding?.length ? (
        <div className="mt-3 overflow-hidden rounded border text-sm">
          <div className="border-b bg-muted/30 px-3 py-2">
            <span className="block text-xs font-medium">Fonti FIFO</span>
            <span className="text-[11px] text-muted-foreground">
              Ordine effettivo di erosione: dall'alto verso il basso, partendo dall'anno più
              vecchio.
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="border-b text-left text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Ordine</th>
                  <th className="px-3 py-2">Progetto origine</th>
                  <th className="px-3 py-2 text-center">Anno</th>
                  <th className="px-3 py-2 text-right">Riservato</th>
                  <th className="px-3 py-2 text-right">Eroso</th>
                  <th className="px-3 py-2 text-right">Residuo</th>
                  <th className="px-3 py-2">Stato</th>
                </tr>
              </thead>
              <tbody>
                {detail.funding.map((tranche) => {
                  const residual = Math.max(
                    0,
                    Number(tranche.impegnato) - Number(tranche.consumato),
                  );
                  const state =
                    residual === 0
                      ? "Esaurita"
                      : Number(tranche.consumato) > 0
                        ? "In erosione"
                        : "Riservata";
                  return (
                    <tr
                      className="border-b last:border-b-0"
                      key={`${tranche.ordine}-${tranche.progetto_origine}`}
                    >
                      <td className="px-3 py-2 font-medium">{tranche.ordine}</td>
                      <td className="max-w-64 px-3 py-2 font-mono" title={tranche.progetto_origine}>
                        <span className="block truncate">{tranche.progetto_origine}</span>
                      </td>
                      <td className="px-3 py-2 text-center">{tranche.anno_provenienza}</td>
                      <td className="px-3 py-2 text-right">
                        <DaysValue value={tranche.impegnato} />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <DaysValue value={tranche.consumato} />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <DaysValue value={residual.toFixed(4)} />
                      </td>
                      <td className="px-3 py-2">{state}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {!canEdit && (
        <div className="mt-4 flex gap-2 rounded border bg-muted/30 p-3 text-sm text-muted-foreground">
          <Lock className="h-4 w-4 shrink-0" /> Consultazione: la modifica richiede la capability
          wallet.edit.
        </div>
      )}

      <form
        className="mt-4 space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          setFormError(null);
          setConflict(false);
          save.mutate();
        }}
      >
        <label className="block text-sm">
          Giornate allocate
          <Input
            className="mt-1 w-full rounded border bg-background p-2 disabled:opacity-60"
            type="number"
            min="0"
            step="0.0001"
            required
            disabled={!canEdit}
            value={allocatedDays}
            onChange={(event) => setAllocatedDays(event.target.value)}
          />
        </label>
        <label className="block text-sm">
          Giornate consumate totali
          <Input
            aria-label="Giornate consumate totali"
            className="mt-1 w-full rounded border bg-background p-2 disabled:opacity-60"
            type="number"
            min="0"
            max={allocatedDays || undefined}
            step="0.0001"
            required
            disabled={!canAdjustConsumed || detail.status === "CHIUSA"}
            value={consumedDays}
            onChange={(event) => setConsumedDays(event.target.value)}
          />
          <span className="mt-1 block text-xs text-muted-foreground">
            Inserisci il totale progressivo consumato. La differenza viene erosa automaticamente
            dalle fonti FIFO nell'ordine mostrato.
          </span>
          {!canAdjustConsumed ? (
            <span className="mt-1 block text-xs text-muted-foreground">
              La modifica richiede il permesso di rettifica dei consuntivi.
            </span>
          ) : null}
        </label>
        <label className="block text-sm">
          Assegnatario
          <Select
            className="mt-1 w-full rounded border bg-background p-2 disabled:opacity-60"
            disabled={!canEdit}
            value={assigneeId}
            onChange={(event) => setAssigneeId(event.target.value)}
          >
            <option value="">Non assegnato</option>
            {architects.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name ?? person.name}
              </option>
            ))}
          </Select>
        </label>
        <label className="block text-sm">
          Stato
          <Select
            className="mt-1 w-full rounded border bg-background p-2 disabled:opacity-60"
            disabled={!canEdit}
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="APERTA">In corso</option>
            <option value="CHIUSA">Chiusa</option>
          </Select>
          {status === "CHIUSA" && detail.status !== "CHIUSA" ? (
            <span className="mt-1 block text-xs text-muted-foreground">
              Alla chiusura, le giornate allocate ma non consumate tornano disponibili nel wallet.
            </span>
          ) : null}
        </label>
        <label className="block text-sm">
          Note
          <Textarea
            aria-label="Note"
            className="mt-1 min-h-24 w-full rounded border bg-background p-2 disabled:opacity-60"
            disabled={!canEdit}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </label>

        {formError && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive"
          >
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{formError}</span>
            {conflict && (
              <Button
                type="button"
                className="ml-auto inline-flex items-center gap-1 underline"
                onClick={() => void allocation.refetch()}
              >
                <RefreshCw className="h-3 w-3" />
                Ricarica
              </Button>
            )}
          </div>
        )}
        {canEdit && (
          <>
            <Button
              type="submit"
              disabled={save.isPending}
              className="w-full rounded bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:opacity-60"
            >
              {save.isPending ? "Salvataggio…" : "Salva"}
            </Button>
            <Button
              type="button"
              onClick={() => {
                setDeleteCode("");
                setDeleteOpen(true);
              }}
              className="flex w-full items-center justify-center gap-2 rounded border border-destructive px-4 py-2 font-medium text-destructive hover:bg-destructive/10"
            >
              <Trash2 className="h-4 w-4" /> Elimina allocazione
            </Button>
          </>
        )}
      </form>
      <Dialog.Root open={deleteOpen} onOpenChange={setDeleteOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(30rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-card p-6 shadow-xl">
            <Dialog.Title className="text-lg font-semibold text-destructive">
              Elimina allocazione
            </Dialog.Title>
            <Dialog.Description className="mt-2 text-sm text-muted-foreground">
              L'eliminazione è possibile solo per allocazioni manuali mai consumate o rettificate.
              Digita <strong className="font-mono">{detail.activity_code}</strong> per confermare.
              Le giornate torneranno nel residuo spendibile del progetto origine.
            </Dialog.Description>
            <Input
              autoFocus
              value={deleteCode}
              onChange={(event) => setDeleteCode(event.target.value)}
              className="mt-4 w-full rounded border bg-background p-2 font-mono"
              aria-label="Codice attività di conferma"
            />
            <div className="mt-5 flex justify-end gap-3">
              <Dialog.Close asChild>
                <Button type="button" className="rounded border px-4 py-2 text-sm">
                  Annulla
                </Button>
              </Dialog.Close>
              <Button
                type="button"
                disabled={deleteCode !== detail.activity_code || remove.isPending}
                onClick={() => remove.mutate()}
                className="rounded bg-danger-action px-4 py-2 text-sm font-semibold text-danger-foreground disabled:opacity-50"
              >
                {remove.isPending ? "Eliminazione…" : "Elimina definitivamente"}
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <p className="mt-3 text-xs text-muted-foreground">
        Versione {detail.version} · anno {year}
      </p>
    </aside>
  );
}
