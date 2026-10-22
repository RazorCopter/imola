import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { DaysValue } from "@/components/DaysValue";
import { KpiCard } from "@/components/KpiCard";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorState, LoadingState } from "@/components/UiState";
import { useSession } from "@/features/auth/session";
import { api } from "@/lib/api";
import { canWriteLedger } from "@/lib/permissions";

interface Balance {
  anno: number;
  allocato: string;
  consumato: string;
  disponibile: string;
  residui_validi_non_allocati: string;
  residui_in_scadenza: string;
  residui_scaduti: string;
  residui_potenziali_da_verificare: string;
  dettaglio_residui: Record<
    string,
    {
      giornate: string;
      progetti: { codice: string; giornate: string; scade_il: string | null; motivo: string }[];
    }
  >;
}
interface Flow {
  id: string;
  riferimento: string;
  origine: string;
  origine_titolo: string;
  destinazione: string;
  destinazione_titolo: string;
  architetto: string | null;
  allocato: string;
  consumato: string;
  disponibile: string;
  stato: string;
}
interface AssigneeTotal {
  architetto_id: string;
  architetto: string;
  allocato: string;
  consumato: string;
  residuo: string;
}
interface Option {
  id: string;
  code?: string;
  title?: string;
  name?: string;
}
interface AllocationOptions {
  projects: Option[];
  activities: Option[];
  assignees: Option[];
}

export function WalletPage() {
  const year = new Date().getFullYear();
  const { session } = useSession();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [sourceProject, setSourceProject] = useState("");
  const [activity, setActivity] = useState("");
  const [assignee, setAssignee] = useState("");
  const [days, setDays] = useState("");
  const [notes, setNotes] = useState("");
  const balance = useQuery({
    queryKey: ["wallet", "balance", year],
    queryFn: () => api.get<Balance>(`/wallet/${year}/balance`),
  });
  const flow = useQuery({
    queryKey: ["wallet", "flow", year],
    queryFn: () => api.get<{ results: Flow[] }>(`/wallet/${year}/flow`),
  });
  const assigneeTotals = useQuery({
    queryKey: ["wallet", "assignees", year],
    queryFn: () => api.get<{ results: AssigneeTotal[] }>(`/wallet/${year}/assignees`),
  });
  const options = useQuery({
    queryKey: ["wallet", "allocation-options"],
    queryFn: () => api.get<AllocationOptions>("/allocations/options"),
    enabled: canWriteLedger(session),
  });
  const create = useMutation({
    mutationFn: () =>
      api.post("/allocations", {
        year,
        source_project: sourceProject,
        activity,
        assignee,
        allocated_days: days,
        notes,
      }),
    onSuccess: async () => {
      setShowCreate(false);
      setDays("");
      setNotes("");
      await queryClient.invalidateQueries({ queryKey: ["wallet"] });
    },
  });
  const adjust = useMutation({
    mutationFn: ({
      id,
      allocated_days,
      status,
    }: {
      id: string;
      allocated_days?: string;
      status?: string;
    }) => api.post(`/allocations/${id}/adjust`, { allocated_days, status }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["wallet"] });
    },
  });
  if (balance.isLoading || flow.isLoading || assigneeTotals.isLoading) return <LoadingState />;
  if (balance.isError || flow.isError || assigneeTotals.isError || !balance.data)
    return <ErrorState title="Impossibile caricare il wallet" />;
  return (
    <section className="space-y-5">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Wallet {year}</h1>
          <p className="text-sm text-muted-foreground">
            Origini, destinazioni e disponibilità calcolate dall’API.
          </p>
        </div>
        {canWriteLedger(session) && (
          <button
            className="bg-primary text-primary-foreground rounded-md px-3 py-2 text-sm font-medium"
            onClick={() => setShowCreate((value) => !value)}
          >
            Nuova allocazione
          </button>
        )}
      </header>
      {showCreate && options.data && (
        <form
          className="grid gap-3 rounded-lg border border-border bg-card p-4 md:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <label className="text-sm">
            Origine
            <select
              className="mt-1 w-full rounded border p-2"
              required
              value={sourceProject}
              onChange={(event) => setSourceProject(event.target.value)}
            >
              <option value="">Seleziona progetto</option>
              {options.data.projects.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.code} — {item.title}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            Progetto / attività
            <select
              className="mt-1 w-full rounded border p-2"
              required
              value={activity}
              onChange={(event) => setActivity(event.target.value)}
            >
              <option value="">Seleziona attività</option>
              {options.data.activities.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.code} — {item.title}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            Architetto
            <select
              className="mt-1 w-full rounded border p-2"
              required
              value={assignee}
              onChange={(event) => setAssignee(event.target.value)}
            >
              <option value="">Seleziona architetto</option>
              {options.data.assignees.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            Giornate
            <input
              className="mt-1 w-full rounded border p-2"
              type="number"
              min="0.0001"
              step="0.0001"
              required
              value={days}
              onChange={(event) => setDays(event.target.value)}
            />
          </label>
          <label className="text-sm md:col-span-2">
            Note
            <textarea
              className="mt-1 w-full rounded border p-2"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </label>
          {create.isError && (
            <p className="text-destructive text-sm md:col-span-2">
              Allocazione non valida o superiore al disponibile.
            </p>
          )}
          <div className="flex justify-end md:col-span-2">
            <button
              className="bg-primary text-primary-foreground rounded-md px-3 py-2 text-sm"
              type="submit"
              disabled={create.isPending}
            >
              Conferma allocazione
            </button>
          </div>
        </form>
      )}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Disponibile"
          value={<DaysValue value={balance.data.disponibile} />}
          tone="ok"
        />
        <KpiCard label="Allocato" value={<DaysValue value={balance.data.allocato} />} />
        <KpiCard label="Consumato" value={<DaysValue value={balance.data.consumato} />} />
        <KpiCard
          label="In scadenza"
          value={<DaysValue value={balance.data.residui_in_scadenza} />}
          tone="warn"
        />
      </div>
      <div className="grid gap-4 xl:grid-cols-[2fr,1fr]">
        <section className="rounded-lg border border-border bg-card p-4">
          <h2 className="font-medium">Flusso origine → attività</h2>
          <div className="mt-3 space-y-2">
            {flow.data?.results.map((row, index) => (
              <div
                key={`${row.origine}-${row.destinazione}-${index}`}
                className="grid gap-2 rounded-md border border-border p-3 sm:grid-cols-[1fr,auto,1fr,auto]"
              >
                <div>
                  <p className="font-mono text-sm">{row.origine}</p>
                  <p className="truncate text-xs text-muted-foreground">{row.origine_titolo}</p>
                </div>
                <span aria-hidden>→</span>
                <div>
                  <p className="font-mono text-sm">{row.destinazione}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {row.destinazione_titolo}
                  </p>
                </div>
                <div className="text-right">
                  <DaysValue value={row.allocato} />
                  <div>
                    <StatusBadge status={row.stato} />
                  </div>
                  {canWriteLedger(session) && (
                    <div className="mt-2 flex justify-end gap-1">
                      <button
                        className="rounded border border-border px-2 py-1 text-[10px]"
                        onClick={() => adjust.mutate({ id: row.id, allocated_days: row.consumato })}
                      >
                        Riduci al consumato
                      </button>
                      <button
                        className="rounded border border-danger/40 px-2 py-1 text-[10px] text-danger"
                        onClick={() => adjust.mutate({ id: row.id, status: "CHIUSA" })}
                      >
                        Chiudi
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
        <aside className="rounded-lg border border-border bg-card p-4">
          <h2 className="font-medium">Residui per validità</h2>
          <div className="mt-3 space-y-4">
            {Object.entries(balance.data.dettaglio_residui).map(([state, bucket]) => (
              <div key={state}>
                <div className="flex items-center justify-between">
                  <StatusBadge status={state} />
                  <DaysValue value={bucket.giornate} />
                </div>
                {bucket.progetti.map((project) => (
                  <div key={project.codice} className="mt-2 border-l-2 border-border pl-2 text-xs">
                    <div className="flex justify-between">
                      <span className="font-mono">{project.codice}</span>
                      <DaysValue value={project.giornate} />
                    </div>
                    <p className="mt-1 text-muted-foreground">
                      {project.scade_il
                        ? `scade ${new Date(`${project.scade_il}T00:00:00`).toLocaleDateString("it-IT")}`
                        : "nessuna scadenza"}
                      {` · ${project.motivo}`}
                    </p>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </aside>
      </div>
    </section>
  );
}
