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
  allocato: string;
  consumato: string;
  disponibile: string;
  stato: string;
}

export function WalletPage() {
  const year = new Date().getFullYear();
  const { session } = useSession();
  const queryClient = useQueryClient();
  const balance = useQuery({
    queryKey: ["wallet", "balance", year],
    queryFn: () => api.get<Balance>(`/wallet/${year}/balance`),
  });
  const flow = useQuery({
    queryKey: ["wallet", "flow", year],
    queryFn: () => api.get<{ results: Flow[] }>(`/wallet/${year}/flow`),
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
  if (balance.isLoading || flow.isLoading) return <LoadingState />;
  if (balance.isError || flow.isError || !balance.data)
    return <ErrorState title="Impossibile caricare il wallet" />;
  return (
    <section className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold">Wallet {year}</h1>
        <p className="text-sm text-muted-foreground">
          Origini, destinazioni e disponibilità calcolate dall’API.
        </p>
      </header>
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
