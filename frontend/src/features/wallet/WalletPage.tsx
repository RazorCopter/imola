import { PageHeader } from "@/components/PageHeader";
import { Button, Input, Select } from "@/components/Controls";
import { useEffect, useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { DaysValue } from "@/components/DaysValue";
import { KpiCard } from "@/components/KpiCard";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorState, LoadingState } from "@/components/UiState";
import { useSession } from "@/features/auth/session";
import { api } from "@/lib/api";
import { canAdjustAccounting, canEditTimesheets, canEditWallet } from "@/lib/permissions";
import { EditAllocationDialog } from "./EditAllocationDialog";
import { NewAllocationDialog } from "./NewAllocationDialog";

interface ResidualProject {
  codice: string;
  giornate: string;
  scade_il: string | null;
  motivo: string;
}
interface Balance {
  anno: number;
  allocato: string;
  totale_allocato?: string;
  allocations_total?: string;
  consumato: string;
  consumato_allocazioni?: string;
  consumed_days?: string;
  disponibile: string;
  disponibile_su_allocazioni?: string;
  available_days?: string;
  disponibile_da_allocazioni?: string;
  disponibile_da_allocazioni_aperte?: string;
  capienza_wallet_potenziale?: string;
  capacita_totale_origini?: string;
  potential_wallet_capacity?: string;
  residuo_wallet_non_allocato?: string;
  unallocated_capacity?: string;
  residui_validi_non_allocati: string;
  residui_in_scadenza: string;
  residui_scaduti: string;
  residui_potenziali_da_verificare: string;
  dettaglio_residui: Record<string, { giornate: string; progetti: ResidualProject[] }>;
}
export interface Flow {
  id: string;
  version: number;
  riferimento: string | null;
  origine: string;
  origine_id?: string | null;
  origine_titolo: string;
  destinazione: string;
  destinazione_titolo: string;
  tipo_attivita: string;
  architetto: string | null;
  allocato: string;
  consumato: string;
  disponibile: string;
  residuo_allocazione: string;
  residuo_spendibile_origine: string | null;
  validita_origine: string | null;
  scadenza_origine: string | null;
  stato: string;
  stato_operativo: "IN_CORSO" | "CHIUSA";
}
interface AssigneeTotal {
  architetto_id: string;
  architetto: string;
  allocato: string;
  consumato: string;
  residuo: string;
}

export function WalletPage() {
  const year = new Date().getFullYear();
  const { session } = useSession();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"IN_CORSO" | "CHIUSA" | "TUTTE">("IN_CORSO");
  const [activityFilter, setActivityFilter] = useState("TUTTE");
  const [selectedId, setSelectedId] = useState<string | null>(null);

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

  const rows = useMemo(() => {
    const term = search.trim().toLocaleLowerCase();
    return (flow.data?.results ?? []).filter((row) => {
      const matchesStatus = statusFilter === "TUTTE" || row.stato_operativo === statusFilter;
      const matchesActivity = activityFilter === "TUTTE" || row.tipo_attivita === activityFilter;
      const haystack = [
        row.riferimento,
        row.origine,
        row.origine_titolo,
        row.destinazione,
        row.destinazione_titolo,
        row.architetto,
      ]
        .filter(Boolean)
        .join(" ")
        .toLocaleLowerCase();
      return matchesStatus && matchesActivity && (!term || haystack.includes(term));
    });
  }, [activityFilter, flow.data?.results, search, statusFilter]);

  useEffect(() => {
    if (selectedId && !flow.data?.results.some((row) => row.id === selectedId)) setSelectedId(null);
  }, [flow.data?.results, selectedId]);

  if (balance.isLoading || flow.isLoading || assigneeTotals.isLoading) return <LoadingState />;
  if (balance.isError || flow.isError || assigneeTotals.isError || !balance.data)
    return <ErrorState title="Impossibile caricare il wallet" />;

  const refreshWallet = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["wallet", "flow", year] }),
      queryClient.invalidateQueries({ queryKey: ["wallet", "balance", year] }),
      queryClient.invalidateQueries({ queryKey: ["wallet", "assignees", year] }),
      queryClient.invalidateQueries({ queryKey: ["wallet", "allocation-options"] }),
    ]);
  };

  const canMutate = canEditWallet(session);
  const canAdjustConsumed = canAdjustAccounting(session) || canEditTimesheets(session);

  return (
    <section className="space-y-5">
      <PageHeader
        eyebrow="Gestione · Capacità"
        title={<>Wallet {year}</>}
        description="Disponibilità, allocazioni e consumi delle attività."
        actions={
          <>
            {canMutate && (
              <NewAllocationDialog
                year={year}
                unallocatedCapacity={
                  balance.data?.residuo_wallet_non_allocato ?? balance.data?.unallocated_capacity
                }
                onCreated={async (id) => {
                  setSelectedId(id);
                  await refreshWallet();
                  await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
                }}
              />
            )}
          </>
        }
      />

      <section aria-label="Situazione del wallet" className="space-y-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Situazione del wallet</h2>
          <p className="text-sm text-muted-foreground">
            Capacità, allocazioni e giornate consumate
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          <KpiCard
            label="Capacità Monte Wallet"
            value={
              <DaysValue
                value={
                  balance.data.capacita_totale_origini ?? balance.data.capienza_wallet_potenziale
                }
              />
            }
            hint="Capacità complessiva rilasciata dai progetti chiusi"
            tooltip="Somma dei residui validi conferiti al wallet dai progetti chiusi. È il monte complessivo da cui possono essere create le allocazioni."
          />
          <KpiCard
            label="Residuo Wallet non allocato"
            value={
              <DaysValue
                value={
                  balance.data.residuo_wallet_non_allocato ?? balance.data.unallocated_capacity
                }
              />
            }
            tone="ok"
            hint="Ancora spendibile per nuove voci di wallet"
            tooltip="Capacità del wallet non ancora assegnata ad attività: capacità totale meno totale allocato."
          />
          <KpiCard
            label="Totale allocato a voci"
            value={<DaysValue value={balance.data.totale_allocato ?? balance.data.allocato} />}
            hint="Giornate complessivamente assegnate ad attività"
            tooltip="Somma delle giornate riservate a tutte le attività wallet, indipendentemente da quanto è già stato consuntivato."
          />
          <KpiCard
            label="Residuo disponibile sulle voci"
            value={
              <DaysValue
                value={balance.data.disponibile_su_allocazioni ?? balance.data.disponibile}
              />
            }
            tone="ok"
            hint="Disponibile da erodere settimanalmente col fornitore"
            tooltip="Giornate ancora disponibili sulle attività già allocate: totale allocato meno giornate consuntivate sulle attività."
          />
          <KpiCard
            label="Consuntivato su voci"
            value={
              <DaysValue value={balance.data.consumato_allocazioni ?? balance.data.consumato} />
            }
            hint="Giornate già erose col fornitore"
            tooltip="Somma dei consuntivi registrati sulle attività wallet. Riduce il rimanente delle relative allocazioni."
          />
        </div>
      </section>

      <div className="grid gap-4">
        <section className="rounded-lg border bg-card p-4" aria-labelledby="allocation-list-title">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 id="allocation-list-title" className="font-medium">
                Allocazioni
              </h2>
              <p className="text-xs text-muted-foreground">Seleziona una riga per il dettaglio.</p>
            </div>
            <span className="text-xs text-muted-foreground">{rows.length} risultati</span>
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-3">
            <label className="text-sm">
              Cerca
              <Input
                aria-label="Cerca allocazioni"
                className="mt-1 w-full rounded border bg-background p-2"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Progetto, attività, assegnatario"
              />
            </label>
            <label className="text-sm">
              Stato allocazione
              <Select
                aria-label="Stato allocazione"
                className="mt-1 w-full rounded border bg-background p-2"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}
              >
                <option value="IN_CORSO">Solo in corso</option>
                <option value="CHIUSA">Solo chiuse</option>
                <option value="TUTTE">Tutte</option>
              </Select>
            </label>
            <label className="text-sm">
              Tipo attività
              <Select
                aria-label="Tipo attività"
                className="mt-1 w-full rounded border bg-background p-2"
                value={activityFilter}
                onChange={(event) => setActivityFilter(event.target.value)}
              >
                <option value="TUTTE">Tutte</option>
                <option value="PROGETTO">Progetto</option>
                <option value="ATTIVITA">Attività</option>
                <option value="REDMINE">Ticket Redmine</option>
              </Select>
            </label>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b text-xs text-muted-foreground">
                <tr>
                  <th className="p-2">Progetto / attività</th>
                  <th className="p-2">Assegnatario</th>
                  <th className="p-2 text-right">Allocato</th>
                  <th className="p-2 text-right">Consumato</th>
                  <th className="p-2 text-right">Residuo allocazione</th>
                  <th className="p-2">Stato</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.id}
                    data-testid={`allocation-row-${row.id}`}
                    tabIndex={0}
                    aria-selected={selectedId === row.id}
                    className={`cursor-pointer border-b outline-none hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-primary ${selectedId === row.id ? "bg-muted" : ""}`}
                    onClick={() => setSelectedId(row.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelectedId(row.id);
                      }
                    }}
                  >
                    <td className="p-2">
                      <div className="font-medium">
                        {row.destinazione_titolo || row.destinazione}
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                        <span className="font-mono">{row.destinazione}</span>
                        <span>•</span>
                        {!row.origine_id || row.origine === "WALLET-GENERALE" ? (
                          <span className="inline-flex items-center rounded bg-secondary/80 px-1.5 py-0.5 text-[11px] font-medium text-secondary-foreground">
                            Origine: Monte Wallet
                          </span>
                        ) : (
                          <span
                            className="inline-flex items-center rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
                            title={row.origine_titolo}
                          >
                            Origine: {row.origine}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="p-2">{row.architetto ?? "—"}</td>
                    <td className="p-2 text-right">
                      <DaysValue value={row.allocato} />
                    </td>
                    <td className="p-2 text-right">
                      <DaysValue value={row.consumato} />
                    </td>
                    <td className="p-2 text-right">
                      <DaysValue value={row.residuo_allocazione ?? row.disponibile} />
                    </td>
                    <td className="p-2">
                      <StatusBadge status={row.stato} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!rows.length && (
              <p className="p-6 text-center text-sm text-muted-foreground">
                Nessuna allocazione per i filtri selezionati.
              </p>
            )}
          </div>
        </section>

        {selectedId && (
          <Dialog.Root
            open
            onOpenChange={(open) => {
              if (!open) setSelectedId(null);
            }}
          >
            <Dialog.Portal>
              <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50" />
              <Dialog.Content
                className="fixed inset-y-0 right-0 z-40 w-[min(42rem,100vw)] overflow-y-auto border-l border-border bg-background p-4 shadow-raised md:p-6"
                onCloseAutoFocus={(event) => {
                  event.preventDefault();
                  document
                    .querySelector<HTMLElement>(`[data-testid="allocation-row-${selectedId}"]`)
                    ?.focus();
                }}
              >
                <div className="mb-4 flex items-center justify-between gap-3">
                  <Dialog.Title className="text-xl font-semibold tracking-tight">
                    Allocazione wallet
                  </Dialog.Title>
                  <Dialog.Close asChild>
                    <Button
                      type="button"
                      className="rounded-md border border-input px-3 py-2 text-sm hover:bg-muted"
                    >
                      Chiudi dettaglio
                    </Button>
                  </Dialog.Close>
                </div>
                <Dialog.Description className="mb-4 text-sm text-muted-foreground">
                  Consulta giornate, fonti e stato della voce selezionata.
                </Dialog.Description>
                <EditAllocationDialog
                  allocationId={selectedId}
                  year={year}
                  canEdit={canMutate}
                  canAdjustConsumed={canAdjustConsumed}
                  onSaved={refreshWallet}
                  onDeleted={async () => {
                    const remaining = (flow.data?.results ?? []).filter(
                      (row) => row.id !== selectedId,
                    );
                    setSelectedId(remaining[0]?.id ?? null);
                    await refreshWallet();
                    await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
                  }}
                />
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
        )}
      </div>

      <section aria-labelledby="residual-validity-title" className="rounded-lg border bg-card p-4">
        <h2 id="residual-validity-title" className="font-medium">
          Residui spendibili delle origini per validità
        </h2>
        <p className="text-xs text-muted-foreground">
          Sono distinti dal residuo delle singole allocazioni (allocato − consumato).
        </p>
        {Object.entries(balance.data.dettaglio_residui).filter(
          ([, bucket]) => Number(bucket.giornate) > 0 || bucket.progetti.length > 0,
        ).length === 0 ? (
          <p className="mt-3 rounded border border-dashed p-4 text-sm text-muted-foreground">
            Nessun residuo origine disponibile.
          </p>
        ) : (
          <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {Object.entries(balance.data.dettaglio_residui)
              .filter(([, bucket]) => Number(bucket.giornate) > 0 || bucket.progetti.length > 0)
              .map(([state, bucket]) => (
                <div key={state} className="rounded border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <StatusBadge status={state} />
                    <DaysValue value={bucket.giornate} />
                  </div>
                  <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                    {bucket.progetti.map((project) => (
                      <li key={`${state}-${project.codice}`}>
                        <strong className="text-foreground">{project.codice}</strong>:{" "}
                        <DaysValue value={project.giornate} />
                        {project.scade_il && (
                          <>
                            {" "}
                            · scade{" "}
                            {new Date(`${project.scade_il}T00:00:00`).toLocaleDateString("it-IT")}
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
          </div>
        )}
      </section>

      <section className="rounded-lg border bg-card p-4">
        <h2 className="font-medium">Totali per assegnatario</h2>
        {assigneeTotals.data?.results?.length === 0 && (
          <p className="mt-3 text-sm text-muted-foreground">
            Nessun totale per assegnatario disponibile.
          </p>
        )}
        <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {(assigneeTotals.data?.results ?? []).map((row) => (
            <div key={row.architetto_id || row.architetto} className="rounded border p-3 text-sm">
              <p className="font-medium">{row.architetto}</p>
              <p className="text-xs text-muted-foreground">
                Residuo allocazioni: <DaysValue value={row.residuo} />
              </p>
            </div>
          ))}
        </div>
      </section>
    </section>
  );
}
