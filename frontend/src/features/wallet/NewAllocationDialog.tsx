import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertCircle, Plus, Wallet } from "lucide-react";
import { useState } from "react";

import { api, ApiError } from "@/lib/api";

interface AllocationOptions {
  activities: { id: string; code: string; title: string }[];
  assignees: { id: string; name: string }[];
  unallocated_capacity?: string;
}

interface Props {
  year: number;
  unallocatedCapacity?: string;
  onCreated: (id: string) => Promise<void>;
}

export function NewAllocationDialog({ year, unallocatedCapacity, onCreated }: Props) {
  const [open, setOpen] = useState(false);
  const [activityMode, setActivityMode] = useState<"EXISTING" | "NEW">("EXISTING");
  const [activity, setActivity] = useState("");
  const [newActivityTitle, setNewActivityTitle] = useState("");
  const [assignee, setAssignee] = useState("");
  const [days, setDays] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const options = useQuery({
    queryKey: ["wallet", "allocation-options", year],
    queryFn: () => api.get<AllocationOptions>(`/wallet/allocation-options/?year=${year}`),
    enabled: open,
  });
  const available = unallocatedCapacity ?? options.data?.unallocated_capacity ?? "0.0000";

  const create = useMutation({
    mutationFn: () => {
      const numericDays = Number(days);
      if (!assignee || !days) throw new Error("Compila tutti i campi obbligatori.");
      if (!Number.isFinite(numericDays) || numericDays <= 0)
        throw new Error("Le giornate devono essere maggiori di zero.");
      if (numericDays > Number(available))
        throw new Error(`Le giornate superano il residuo del Monte Wallet (${available} gg).`);
      if (activityMode === "NEW" && !newActivityTitle.trim())
        throw new Error("Inserisci il nome della nuova attività.");
      if (activityMode === "EXISTING" && !activity)
        throw new Error("Seleziona un'attività destinazione.");
      return api.post<{ id: string }>("/allocations", {
        year,
        assignee,
        allocated_days: String(numericDays),
        notes: notes.trim(),
        ...(activityMode === "NEW"
          ? { new_activity_title: newActivityTitle.trim() }
          : { activity }),
      });
    },
    onSuccess: async (created) => {
      await onCreated(created.id);
      setOpen(false);
      setActivity("");
      setNewActivityTitle("");
      setAssignee("");
      setDays("");
      setNotes("");
      setError(null);
    },
    onError: (cause: unknown) => {
      if (cause instanceof ApiError) {
        const fields = cause.problem.errors?.map((item) => item.messaggio).join("; ");
        setError(fields || cause.problem.detail || cause.message);
      } else setError(cause instanceof Error ? cause.message : "Errore durante la creazione.");
    },
  });

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button className="inline-flex items-center gap-2 rounded bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700">
          <Plus className="h-4 w-4" /> Nuovo utilizzo
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[min(38rem,calc(100%-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border bg-card p-6 shadow-xl">
          <Dialog.Title className="text-lg font-semibold">Nuovo utilizzo wallet</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-muted-foreground">
            Le fonti vengono attribuite automaticamente in FIFO: anno precedente, data, codice.
          </Dialog.Description>
          <form
            className="mt-5 space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              setError(null);
              create.mutate();
            }}
          >
            <label className="block text-sm">
              Anno
              <input value={year} readOnly className="mt-1 w-full rounded border bg-muted p-2" />
            </label>
            <div className="border-primary/30 bg-primary/5 rounded border p-3 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 font-medium">
                  <Wallet className="h-4 w-4" /> Monte Wallet FIFO
                </span>
                <strong className="text-primary">{available} gg</strong>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Le singole fonti restano visibili come tranche nel dettaglio dell'utilizzo.
              </p>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Attività destinataria *</span>
                <button
                  type="button"
                  className="text-primary text-xs underline"
                  onClick={() => setActivityMode(activityMode === "NEW" ? "EXISTING" : "NEW")}
                >
                  {activityMode === "NEW" ? "Seleziona esistente" : "+ Nuova attività"}
                </button>
              </div>
              {activityMode === "NEW" ? (
                <input
                  required
                  value={newActivityTitle}
                  onChange={(event) => setNewActivityTitle(event.target.value)}
                  placeholder="Nome attività"
                  className="w-full rounded border bg-background p-2 text-sm"
                />
              ) : (
                <select
                  required
                  value={activity}
                  onChange={(event) => setActivity(event.target.value)}
                  className="w-full rounded border bg-background p-2 text-sm"
                >
                  <option value="">Seleziona attività</option>
                  {options.data?.activities?.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.code} · {item.title}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <label className="block text-sm">
              Assegnatario *
              <select
                required
                value={assignee}
                onChange={(event) => setAssignee(event.target.value)}
                className="mt-1 w-full rounded border bg-background p-2"
              >
                <option value="">Seleziona assegnatario</option>
                {options.data?.assignees?.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              Giornate da riservare *
              <input
                required
                type="number"
                min="0.0001"
                step="0.0001"
                max={Number(available) > 0 ? available : undefined}
                value={days}
                onChange={(event) => setDays(event.target.value)}
                className="mt-1 w-full rounded border bg-background p-2"
              />
            </label>
            <label className="block text-sm">
              Note
              <textarea
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                className="mt-1 min-h-20 w-full rounded border bg-background p-2"
              />
            </label>
            {error && (
              <div
                role="alert"
                className="border-destructive/40 bg-destructive/10 text-destructive flex gap-2 rounded border p-3 text-sm"
              >
                <AlertCircle className="h-4 w-4 shrink-0" /> {error}
              </div>
            )}
            <div className="flex justify-end gap-3 border-t pt-4">
              <Dialog.Close asChild>
                <button type="button" className="rounded border px-4 py-2 text-sm">
                  Annulla
                </button>
              </Dialog.Close>
              <button
                type="submit"
                disabled={create.isPending}
                className="rounded bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                {create.isPending ? "Creazione..." : "Crea utilizzo"}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
