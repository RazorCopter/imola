import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { AlertCircle, Lock, RefreshCw, X } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { useSession } from "@/features/auth/session";
import { canAdjustAccounting, canEditWallet } from "@/lib/permissions";

export interface TimesheetEntryItem {
  id: string;
  period: string | null;
  days: string;
  source: string;
  note: string;
  reverses_id: string | null;
}

export interface WalletAllocationDetail {
  id: string;
  version: number;
  external_ref: string | null;
  allocated_days: string;
  days_allocated: string;
  consumed_days: string;
  available_days: string;
  status: string;
  notes: string;
  assignee: string | null;
  architetto: string | null;
  source_project: string | null;
  source_project_code: string | null;
  source_project_title: string | null;
  activity: string;
  activity_code: string;
  activity_title: string;
  year: number;
  timesheet_entries: TimesheetEntryItem[];
}

interface AllocationOptions {
  projects: { id: string; code?: string; title?: string }[];
  activities: { id: string; code?: string; title?: string }[];
  assignees: { id: string; name: string; full_name?: string }[];
  architects?: { id: string; name: string; full_name?: string }[];
}

interface EditAllocationDialogProps {
  allocationId: string | null;
  year: number;
  onClose: () => void;
}

export function EditAllocationDialog({ allocationId, year, onClose }: EditAllocationDialogProps) {
  const queryClient = useQueryClient();
  const { session } = useSession();

  const userCanEdit = canEditWallet(session);
  const userCanAdjust = canAdjustAccounting(session);

  const [allocatedDays, setAllocatedDays] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const [status, setStatus] = useState("APERTA");
  const [notes, setNotes] = useState("");

  // Sezione storno/rettifica append-only consuntivi
  const [showAdjustSection, setShowAdjustSection] = useState(false);
  const [selectedEntryId, setSelectedEntryId] = useState("");
  const [newConsumedDays, setNewConsumedDays] = useState("");
  const [adjustNote, setAdjustNote] = useState("");

  const [conflictError, setConflictError] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const allocationQuery = useQuery({
    queryKey: ["wallet", "allocation", allocationId],
    queryFn: () => api.get<WalletAllocationDetail>(`/wallet/allocations/${allocationId}/`),
    enabled: Boolean(allocationId),
  });

  const optionsQuery = useQuery({
    queryKey: ["wallet", "allocation-options"],
    queryFn: () => api.get<AllocationOptions>("/wallet/allocation-options/"),
    enabled: Boolean(allocationId),
  });

  const alloc = allocationQuery.data;

  useEffect(() => {
    if (alloc) {
      setAllocatedDays(alloc.allocated_days || alloc.days_allocated || "");
      setAssigneeId(alloc.assignee || "");
      setStatus(alloc.status || "APERTA");
      setNotes(alloc.notes || "");
      setConflictError(false);
      setFormError(null);
      setShowAdjustSection(false);
      setSelectedEntryId("");
      setNewConsumedDays("");
      setAdjustNote("");
    }
  }, [alloc]);

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!alloc || !allocationId) return;

      const payload: Record<string, unknown> = {
        expected_version: alloc.version,
        allocated_days: allocatedDays.trim(),
        assignee: assigneeId ? assigneeId : null,
        status: status,
        notes: notes.trim(),
      };

      if (showAdjustSection && selectedEntryId) {
        payload.adjust_timesheet = {
          reversal_entry_id: selectedEntryId,
          new_days: newConsumedDays.trim(),
          note: adjustNote.trim(),
        };
      }

      return api.patch(`/wallet/allocations/${allocationId}/`, payload, {
        headers: {
          "If-Match": `"${alloc.version}"`,
        },
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["wallet", "flow", year] });
      void queryClient.invalidateQueries({ queryKey: ["wallet", "balance", year] });
      queryClient.invalidateQueries({ queryKey: ["wallet", "assignees", year] }).catch(() => {});
      void queryClient.invalidateQueries({ queryKey: ["wallet", "allocation", allocationId] });
      onClose();
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError && err.status === 409) {
        setConflictError(true);
        setFormError(
          "La risorsa è stata modificata nel frattempo da un altro utente. Ricarica i dati aggiornati per riprovare.",
        );
        return;
      }
      if (err instanceof ApiError) {
        const body = err.problem;
        const msg = body?.detail || body?.title || err.message;
        setFormError(msg || "Errore durante il salvataggio.");
        return;
      }
      setFormError("Si è verificato un errore inatteso.");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setConflictError(false);
    updateMutation.mutate();
  };

  const handleReload = () => {
    setConflictError(false);
    setFormError(null);
    void allocationQuery.refetch();
  };

  if (!allocationId) return null;

  const architects = optionsQuery.data?.architects || optionsQuery.data?.assignees || [];

  return (
    <Dialog.Root open={Boolean(allocationId)} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-sm transition-opacity" />
        <Dialog.Content
          aria-describedby="edit-allocation-description"
          className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-border bg-card p-6 shadow-xl focus:outline-none"
        >
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div>
              <Dialog.Title className="text-lg font-semibold text-foreground">
                Modifica Allocazione Wallet
              </Dialog.Title>
              <p id="edit-allocation-description" className="text-xs text-muted-foreground">
                {alloc
                  ? `${alloc.source_project_code || "WALLET-GENERALE"} → ${alloc.activity_code} (${alloc.activity_title})`
                  : "Caricamento in corso..."}
              </p>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                aria-label="Chiudi"
              >
                <X className="h-5 w-5" />
              </button>
            </Dialog.Close>
          </div>

          {allocationQuery.isLoading ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              Caricamento dati allocazione...
            </div>
          ) : !alloc ? (
            <div className="py-8 text-center text-sm text-danger">
              Impossibile caricare i dati dell'allocazione.
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="mt-4 space-y-4">
              {conflictError && (
                <div className="flex items-start justify-between rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-500">
                  <div className="flex items-center gap-2">
                    <AlertCircle className="h-5 w-5 shrink-0" />
                    <span>{formError}</span>
                  </div>
                  <button
                    type="button"
                    onClick={handleReload}
                    className="ml-3 inline-flex items-center gap-1 rounded border border-amber-500/40 bg-amber-500/20 px-2 py-1 text-xs font-medium hover:bg-amber-500/30"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    Ricarica
                  </button>
                </div>
              )}

              {!conflictError && formError && (
                <div className="border-destructive/40 bg-destructive/10 text-destructive flex items-center gap-2 rounded-md border p-3 text-sm">
                  <AlertCircle className="h-5 w-5 shrink-0" />
                  <span>{formError}</span>
                </div>
              )}

              {/* Informazioni di sola lettura sull'origine e destinazione */}
              <div className="grid grid-cols-2 gap-3 rounded-md bg-muted/40 p-3 text-xs">
                <div>
                  <span className="font-semibold text-muted-foreground">Progetto Origine:</span>
                  <p className="font-mono text-foreground">
                    {alloc.source_project_code || "WALLET-GENERALE"}
                  </p>
                  <p className="truncate text-muted-foreground">
                    {alloc.source_project_title || "Nessun progetto"}
                  </p>
                </div>
                <div>
                  <span className="font-semibold text-muted-foreground">Attività Wallet:</span>
                  <p className="font-mono text-foreground">{alloc.activity_code}</p>
                  <p className="truncate text-muted-foreground">{alloc.activity_title}</p>
                </div>
                <div>
                  <span className="font-semibold text-muted-foreground">Consumato attuale:</span>
                  <p className="font-mono text-foreground">{alloc.consumed_days} gg</p>
                </div>
                <div>
                  <span className="font-semibold text-muted-foreground">Disponibile residuo:</span>
                  <p className="font-mono text-foreground">{alloc.available_days} gg</p>
                </div>
              </div>

              {/* Campi modificabili */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label
                    htmlFor="allocated_days_input"
                    className="block text-xs font-medium text-foreground"
                  >
                    Giornate allocate <span className="text-danger">*</span>
                  </label>
                  <input
                    id="allocated_days_input"
                    type="number"
                    step="0.0001"
                    min="0"
                    required
                    disabled={!userCanEdit}
                    value={allocatedDays}
                    onChange={(e) => setAllocatedDays(e.target.value)}
                    className="focus:border-primary mt-1 w-full rounded border border-border bg-background px-3 py-1.5 font-mono text-sm focus:outline-none disabled:opacity-50"
                  />
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    Non può essere inferiore al consumato ({alloc.consumed_days} gg).
                  </p>
                </div>

                <div>
                  <label
                    htmlFor="assignee_select"
                    className="block text-xs font-medium text-foreground"
                  >
                    Architetto Assegnatario
                  </label>
                  <select
                    id="assignee_select"
                    disabled={!userCanEdit}
                    value={assigneeId}
                    onChange={(e) => setAssigneeId(e.target.value)}
                    className="focus:border-primary mt-1 w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none disabled:opacity-50"
                  >
                    <option value="">Non assegnato</option>
                    {architects.map((person) => (
                      <option key={person.id} value={person.id}>
                        {person.name || person.full_name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label
                    htmlFor="status_select"
                    className="block text-xs font-medium text-foreground"
                  >
                    Stato Allocazione
                  </label>
                  <select
                    id="status_select"
                    disabled={!userCanEdit}
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                    className="focus:border-primary mt-1 w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none disabled:opacity-50"
                  >
                    <option value="APERTA">APERTA</option>
                    <option value="CHIUSA">CHIUSA</option>
                  </select>
                </div>

                <div>
                  <label
                    htmlFor="notes_input"
                    className="block text-xs font-medium text-foreground"
                  >
                    Note allocazione
                  </label>
                  <input
                    id="notes_input"
                    type="text"
                    disabled={!userCanEdit}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Note facoltative"
                    className="focus:border-primary mt-1 w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none disabled:opacity-50"
                  />
                </div>
              </div>

              {/* Sezione Rettifica Consuntivi (Append-Only) */}
              {userCanAdjust && alloc.timesheet_entries.length > 0 && (
                <div className="mt-4 rounded-md border border-border/80 bg-muted/20 p-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="text-xs font-semibold text-foreground">
                        Rettifica Consuntivi (Ledger Append-Only)
                      </h4>
                      <p className="text-[11px] text-muted-foreground">
                        Storno transazionale contabile e nuova emissione senza sovrascritture.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setShowAdjustSection((v) => !v)}
                      className="rounded border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                    >
                      {showAdjustSection ? "Annulla rettifica" : "Rettifica consuntivo"}
                    </button>
                  </div>

                  {showAdjustSection && (
                    <div className="mt-3 space-y-3 border-t border-border/60 pt-3 text-xs">
                      <div>
                        <label htmlFor="entry_select" className="block font-medium text-foreground">
                          Seleziona voce consuntivo da stornare
                        </label>
                        <select
                          id="entry_select"
                          value={selectedEntryId}
                          onChange={(e) => {
                            setSelectedEntryId(e.target.value);
                            const entry = alloc.timesheet_entries.find(
                              (item) => item.id === e.target.value,
                            );
                            if (entry) {
                              setNewConsumedDays(entry.days);
                              setAdjustNote(
                                `Rettifica consuntivo periodo ${entry.period || "n.d."}`,
                              );
                            }
                          }}
                          className="mt-1 w-full rounded border border-border bg-background p-1.5 font-mono text-xs"
                        >
                          <option value="">Seleziona un consuntivo...</option>
                          {alloc.timesheet_entries
                            .filter((item) => Number(item.days) > 0)
                            .map((item) => (
                              <option key={item.id} value={item.id}>
                                Periodo: {item.period || "n.d."} — {item.days} gg ({item.source})
                              </option>
                            ))}
                        </select>
                      </div>

                      {selectedEntryId && (
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <div>
                            <label
                              htmlFor="new_days_input"
                              className="block font-medium text-foreground"
                            >
                              Nuovo valore consuntivato (gg)
                            </label>
                            <input
                              id="new_days_input"
                              type="number"
                              step="0.0001"
                              min="0"
                              value={newConsumedDays}
                              onChange={(e) => setNewConsumedDays(e.target.value)}
                              className="mt-1 w-full rounded border border-border bg-background p-1.5 font-mono text-xs"
                            />
                          </div>
                          <div>
                            <label
                              htmlFor="adj_note_input"
                              className="block font-medium text-foreground"
                            >
                              Motivazione rettifica
                            </label>
                            <input
                              id="adj_note_input"
                              type="text"
                              value={adjustNote}
                              onChange={(e) => setAdjustNote(e.target.value)}
                              className="mt-1 w-full rounded border border-border bg-background p-1.5 text-xs"
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              <div className="flex items-center justify-between border-t border-border pt-4">
                <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                  <Lock className="h-3 w-3" /> Lock ottimistico versione #{alloc.version}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={onClose}
                    className="rounded border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
                  >
                    Annulla
                  </button>
                  <button
                    type="submit"
                    disabled={updateMutation.isPending || !userCanEdit}
                    data-testid="submit-edit-allocation"
                    className="inline-flex items-center justify-center rounded bg-amber-500 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-950 shadow-sm transition-colors hover:bg-amber-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-500 disabled:opacity-50"
                  >
                    {updateMutation.isPending ? "Salvataggio..." : "Salva Modifiche"}
                  </button>
                </div>
              </div>
            </form>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
