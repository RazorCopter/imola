import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Tabs from "@radix-ui/react-tabs";
import { Link, useParams } from "react-router-dom";

import { DaysValue } from "@/components/DaysValue";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/UiState";
import { useSession } from "@/features/auth/session";
import { api } from "@/lib/api";
import { canCreateTimesheets, canEditProjects } from "@/lib/permissions";
import { EditProjectDialog } from "./EditProjectDialog";
import type { ProjectBalance } from "./ProjectsPage";

interface ProjectLedger {
  consuntivi: {
    id: string;
    periodo: string;
    giornate: string;
    descrizione: string;
    utente: string;
  }[];
  wallet: {
    id: string;
    codice: string;
    attivita: string;
    assegnatario: string | null;
    allocato: string;
    consumato: string;
    rimanente: string;
    stato: string;
  }[];
}

export function ProjectDetailPage() {
  const { projectId } = useParams();
  const client = useQueryClient();
  const { session } = useSession();
  const [editOpen, setEditOpen] = useState(false);
  const [timesheetOpen, setTimesheetOpen] = useState(false);
  const [days, setDays] = useState("");
  const [description, setDescription] = useState("");
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 10));

  const query = useQuery({
    queryKey: ["projects", "balances"],
    queryFn: () => api.get<{ results: ProjectBalance[] }>("/projects/balances"),
  });
  const ledger = useQuery({
    queryKey: ["projects", projectId, "ledger"],
    queryFn: () => api.get<ProjectLedger>(`/projects/${projectId}/ledger`),
    enabled: Boolean(projectId),
  });
  const audit = useQuery({
    queryKey: ["audit", "project", projectId],
    queryFn: () =>
      api.get<{
        results: {
          history_id: number;
          data: string;
          tipo: string;
          utente: string;
          modifiche: string[];
        }[];
      }>(`/audit/project/${projectId}`),
    enabled: Boolean(projectId),
  });
  const update = useMutation({
    mutationFn: (payload: { planned_end_date?: string }) =>
      api.patch(`/projects/${projectId}`, payload),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["projects"] });
      await client.invalidateQueries({ queryKey: ["audit", "project", projectId] });
    },
  });
  const createTimesheet = useMutation({
    mutationFn: () =>
      api.post(`/projects/${projectId}/ledger`, {
        giornate: days,
        descrizione: description,
        periodo: period,
      }),
    onSuccess: async () => {
      setDays("");
      setDescription("");
      setTimesheetOpen(false);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["projects", projectId, "ledger"] }),
        client.invalidateQueries({ queryKey: ["projects", "balances"] }),
      ]);
    },
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState title="Impossibile caricare il progetto" />;
  const project = query.data?.results.find((item) => item.id === projectId);
  if (!project) return <EmptyState title="Progetto non trovato" />;

  const metrics = [
    ["Budget", project.budget],
    ["Consuntivi diretti (progetto)", project.consuntivi_diretti],
    ["Consumato da wallet", project.consumato_via_wallet],
    ["Consumato totale", project.consumato_totale],
    ["Rimanente allocato wallet", project.rimanente_allocato_wallet],
    ["Residuo", project.residuo],
  ] as const;
  const timesheets = ledger.data?.consuntivi ?? [];
  const walletActivities = ledger.data?.wallet ?? [];
  const tabs = ["Panoramica", "Consuntivi", "Wallet", "Anomalie", "Storico modifiche"];

  return (
    <section className="space-y-5">
      <header>
        <Link to="/progetti" className="text-sm text-accent">
          ← Progetti
        </Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-mono text-xl font-semibold">{project.codice}</h1>
            <StatusBadge status={project.stato_consuntivazione} domain="timesheet" />
            <StatusBadge status={project.stato_fatturazione} domain="billing" />
            <StatusBadge status={project.stato_offerta} domain="offer" />
          </div>
          {(canEditProjects(session) ||
            project.permissions?.edit ||
            project.permissions?.annotate) && (
            <button
              type="button"
              onClick={() => setEditOpen(true)}
              data-testid="edit-project-detail-button"
              className="rounded bg-amber-500 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-950 hover:bg-amber-400"
            >
              Edit progetto
            </button>
          )}
        </div>
        <p className="mt-1 text-muted-foreground">{project.titolo}</p>
      </header>

      {editOpen && projectId && (
        <EditProjectDialog projectId={projectId} open={editOpen} onOpenChange={setEditOpen} />
      )}
      <Tabs.Root defaultValue="Panoramica">
        <Tabs.List
          className="flex gap-1 overflow-x-auto border-b border-border"
          aria-label="Dettaglio progetto"
        >
          {tabs.map((tab) => (
            <Tabs.Trigger
              key={tab}
              value={tab}
              className="whitespace-nowrap border-b-2 border-transparent px-3 py-2 text-sm text-muted-foreground data-[state=active]:border-accent data-[state=active]:text-foreground"
            >
              {tab}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        <Tabs.Content value="Panoramica" className="space-y-4 pt-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {metrics.map(([label, value]) => (
              <article key={label} className="rounded-lg border border-border bg-card p-4">
                <p className="text-xs uppercase text-muted-foreground">{label}</p>
                <DaysValue
                  value={value}
                  label={label}
                  className="mt-2 block font-mono text-xl font-semibold tabular-nums"
                />
              </article>
            ))}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <article className="rounded-lg border border-border bg-card p-4">
              <p className="text-xs uppercase text-muted-foreground">Data inizio</p>
              <p className="mt-2 font-medium">{project.data_inizio ?? "—"}</p>
            </article>
            <article className="rounded-lg border border-border bg-card p-4">
              <p className="text-xs uppercase text-muted-foreground">Data fine prevista</p>
              <p className="mt-2 font-medium">{project.data_fine_prevista ?? "—"}</p>
            </article>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <h2 className="font-medium">Validità residuo</h2>
            <div className="mt-2 flex items-center gap-3">
              <StatusBadge status={project.stato_residuo} />
              <span className="text-sm text-muted-foreground">{project.residuo_motivo}</span>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{project.spiegazione_residuo}</p>
          </div>
        </Tabs.Content>

        <Tabs.Content value="Consuntivi" className="space-y-4 pt-4">
          {canCreateTimesheets(session) && (
            <button
              type="button"
              onClick={() => setTimesheetOpen((value) => !value)}
              className="rounded bg-accent px-4 py-2 text-sm font-medium text-accent-foreground"
            >
              Consuntiva
            </button>
          )}
          {timesheetOpen && (
            <form
              className="grid gap-3 rounded-lg border border-border bg-card p-4 md:grid-cols-[10rem_12rem_1fr_auto] md:items-end"
              onSubmit={(event) => {
                event.preventDefault();
                createTimesheet.mutate();
              }}
            >
              <label className="text-sm">
                Giornate
                <input
                  aria-label="Giornate"
                  type="number"
                  min="0.01"
                  step="0.01"
                  required
                  value={days}
                  onChange={(event) => setDays(event.target.value)}
                  className="mt-1 w-full rounded border border-input bg-background px-3 py-2"
                />
              </label>
              <label className="text-sm">
                Periodo
                <input
                  aria-label="Periodo"
                  type="date"
                  required
                  value={period}
                  onChange={(event) => setPeriod(event.target.value)}
                  className="mt-1 w-full rounded border border-input bg-background px-3 py-2"
                />
              </label>
              <label className="text-sm">
                Descrizione
                <input
                  aria-label="Descrizione"
                  type="text"
                  maxLength={300}
                  required
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  className="mt-1 w-full rounded border border-input bg-background px-3 py-2"
                />
              </label>
              <button
                type="submit"
                disabled={createTimesheet.isPending}
                className="bg-primary text-primary-foreground rounded px-4 py-2 text-sm disabled:opacity-50"
              >
                {createTimesheet.isPending ? "Salvataggio…" : "Salva"}
              </button>
            </form>
          )}
          {createTimesheet.isError && (
            <p role="alert" className="text-destructive text-sm">
              Impossibile registrare il consuntivo. Verifica giornate e descrizione.
            </p>
          )}
          {ledger.isLoading ? (
            <LoadingState />
          ) : timesheets.length ? (
            <div className="overflow-x-auto rounded-lg border border-border bg-card">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-left">
                  <tr>
                    <th className="p-3">Periodo</th>
                    <th className="p-3">Utente</th>
                    <th className="p-3 text-right">Giornate</th>
                    <th className="p-3">Descrizione</th>
                  </tr>
                </thead>
                <tbody>
                  {timesheets.map((entry) => (
                    <tr key={entry.id} className="border-t border-border">
                      <td className="p-3">{entry.periodo}</td>
                      <td className="p-3">{entry.utente}</td>
                      <td className="p-3 text-right">
                        <DaysValue value={entry.giornate} />
                      </td>
                      <td className="p-3">{entry.descrizione || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="Nessun consuntivo registrato" />
          )}
        </Tabs.Content>

        <Tabs.Content value="Wallet" className="pt-4">
          {ledger.isLoading ? (
            <LoadingState />
          ) : walletActivities.length ? (
            <div className="overflow-x-auto rounded-lg border border-border bg-card">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-left">
                  <tr>
                    <th className="p-3">Attività figlia</th>
                    <th className="p-3">Assegnatario</th>
                    <th className="p-3 text-right">Allocato</th>
                    <th className="p-3 text-right">Consumato</th>
                    <th className="p-3 text-right">Rimanente</th>
                    <th className="p-3">Stato</th>
                  </tr>
                </thead>
                <tbody>
                  {walletActivities.map((item) => (
                    <tr key={item.id} className="border-t border-border">
                      <td className="p-3">
                        <span className="font-mono">{item.codice}</span>
                        <br />
                        <span className="text-xs text-muted-foreground">{item.attivita}</span>
                      </td>
                      <td className="p-3">{item.assegnatario ?? "—"}</td>
                      <td className="p-3 text-right">
                        <DaysValue value={item.allocato} />
                      </td>
                      <td className="p-3 text-right">
                        <DaysValue value={item.consumato} />
                      </td>
                      <td className="p-3 text-right">
                        <DaysValue value={item.rimanente} />
                      </td>
                      <td className="p-3">
                        <StatusBadge status={item.stato} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="Nessuna attività wallet finanziata da questo progetto" />
          )}
        </Tabs.Content>

        <Tabs.Content value="Anomalie" className="pt-4">
          {project.permissions?.annotate ? (
            <div className="rounded-lg border border-border bg-card p-4">
              <h2 className="font-medium">Azioni sul progetto</h2>
              <div className="mt-3 flex flex-wrap gap-2">
                <input
                  id="planned-end-date"
                  type="date"
                  defaultValue={project.data_fine_prevista ?? ""}
                  className="rounded border border-input bg-background px-3 py-2 text-sm"
                />
                <button
                  className="rounded bg-accent px-3 py-2 text-sm font-medium text-accent-foreground"
                  onClick={() => {
                    const input = document.getElementById("planned-end-date") as HTMLInputElement;
                    update.mutate({ planned_end_date: input.value });
                  }}
                >
                  Aggiorna data fine prevista
                </button>
              </div>
            </div>
          ) : (
            <p className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
              Consultazione disponibile; le modifiche non sono consentite per questo progetto.
            </p>
          )}
        </Tabs.Content>

        <Tabs.Content value="Storico modifiche" className="pt-4">
          {audit.isLoading ? (
            <LoadingState />
          ) : audit.data?.results.length ? (
            <div className="space-y-2">
              {audit.data.results.map((record) => (
                <article
                  key={record.history_id}
                  className="rounded-lg border border-border bg-card p-4 text-sm"
                >
                  <div className="flex justify-between gap-3">
                    <span className="font-medium">{record.tipo}</span>
                    <time className="text-xs text-muted-foreground">
                      {new Date(record.data).toLocaleString("it-IT")}
                    </time>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">Utente: {record.utente}</p>
                  <ul className="mt-2 list-disc pl-5 text-xs">
                    {record.modifiche.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState title="Nessuna modifica registrata" />
          )}
        </Tabs.Content>
      </Tabs.Root>
    </section>
  );
}
