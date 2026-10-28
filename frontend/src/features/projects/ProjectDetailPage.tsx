import { Button, Input } from "@/components/Controls";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Tabs from "@radix-ui/react-tabs";
import { Link, useParams } from "react-router-dom";

import { DaysValue } from "@/components/DaysValue";
import { MetricLabel } from "@/components/InfoTooltip";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/UiState";
import { useSession } from "@/features/auth/session";
import { api } from "@/lib/api";
import { canCreateTimesheets, canEditTimesheets, canEditProjects } from "@/lib/permissions";
import { EditProjectDialog } from "./EditProjectDialog";
import type { ProjectBalance } from "./ProjectsPage";

interface ProjectLedger {
  consuntivi: {
    id: string;
    data: string;
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
  const [editingTimesheetId, setEditingTimesheetId] = useState<string | null>(null);
  const [days, setDays] = useState("");
  const [description, setDescription] = useState("");
  const [entryDate, setEntryDate] = useState(new Date().toISOString().slice(0, 10));

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
        data: entryDate,
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
  const refreshTimesheets = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["projects", projectId, "ledger"] }),
      client.invalidateQueries({ queryKey: ["projects", "balances"] }),
    ]);
  };
  const updateTimesheet = useMutation({
    mutationFn: () =>
      api.patch(`/projects/${projectId}/ledger/${editingTimesheetId}`, {
        giornate: days,
        descrizione: description,
        data: entryDate,
      }),
    onSuccess: async () => {
      setDays("");
      setDescription("");
      setEditingTimesheetId(null);
      setTimesheetOpen(false);
      await refreshTimesheets();
    },
  });
  const deleteTimesheet = useMutation({
    mutationFn: (entryId: string) => api.delete(`/projects/${projectId}/ledger/${entryId}`),
    onSuccess: refreshTimesheets,
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState title="Impossibile caricare il progetto" />;
  const project = query.data?.results.find((item) => item.id === projectId);
  if (!project) return <EmptyState title="Progetto non trovato" />;

  const metrics = [
    ["Budget", project.budget, "Monte giornate complessivo previsto per il progetto."],
    [
      "Consuntivi diretti (progetto)",
      project.consuntivi_diretti,
      "Giornate registrate direttamente sul progetto, inclusi eventuali storni.",
    ],
    [
      "Consumato da wallet",
      project.consumato_via_wallet,
      "Giornate consuntivate sulle attività wallet finanziate dal residuo di questo progetto.",
    ],
    [
      "Consumato totale",
      project.consumato_totale,
      "Somma dei consuntivi diretti e delle giornate consumate tramite attività wallet.",
    ],
    [
      "Rimanente allocato wallet",
      project.rimanente_allocato_wallet,
      "Giornate già riservate alle attività wallet ma non ancora consuntivate: allocato meno consumato.",
    ],
    [
      "Residuo",
      project.residuo,
      "Per un progetto in corso è il budget operativo residuo; per un progetto chiuso è la quota wallet ancora non allocata.",
    ],
  ] as const;
  const timesheets = ledger.data?.consuntivi ?? [];
  const walletActivities = ledger.data?.wallet ?? [];
  const tabs = ["Panoramica", "Consuntivi", "Wallet", "Anomalie", "Storico modifiche"];

  return (
    <section className="space-y-5">
      <header className="rounded-2xl border border-border bg-card p-6 md:p-7">
        <Link to="/progetti" className="text-sm text-accent">
          ← Progetti
        </Link>
        <div className="mt-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="break-all text-xs font-medium text-muted-foreground">{project.codice}</p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight">{project.titolo}</h1>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <StatusBadge status={project.stato_consuntivazione} domain="timesheet" />
              <StatusBadge status={project.stato_fatturazione} domain="billing" />
              <StatusBadge status={project.stato_offerta} domain="offer" />
            </div>
          </div>
          {(canEditProjects(session) ||
            project.permissions?.edit ||
            project.permissions?.annotate) && (
            <Button
              type="button"
              onClick={() => setEditOpen(true)}
              data-testid="edit-project-detail-button"
              className="rounded bg-amber-500 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-950 hover:bg-amber-400"
            >
              Edit progetto
            </Button>
          )}
        </div>
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
            {metrics.map(([label, value, description]) => (
              <article key={label} className="rounded-lg border border-border bg-card p-4">
                <MetricLabel label={label} description={description} />
                <DaysValue
                  value={value}
                  label={label}
                  className="mt-3 block text-xl font-semibold tabular-nums tracking-tight"
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
            <Button
              type="button"
              onClick={() => {
                setEditingTimesheetId(null);
                setDays("");
                setDescription("");
                setEntryDate(new Date().toISOString().slice(0, 10));
                setTimesheetOpen((value) => !value);
              }}
              className="rounded bg-accent px-4 py-2 text-sm font-medium text-accent-foreground"
            >
              Consuntiva
            </Button>
          )}
          {timesheetOpen && (
            <form
              className="grid gap-3 rounded-lg border border-border bg-card p-4 md:grid-cols-[10rem_12rem_1fr_auto] md:items-end"
              onSubmit={(event) => {
                event.preventDefault();
                if (editingTimesheetId) updateTimesheet.mutate();
                else createTimesheet.mutate();
              }}
            >
              <label className="text-sm">
                Giornate
                <Input
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
                Data
                <Input
                  aria-label="Data"
                  type="date"
                  required
                  value={entryDate}
                  onChange={(event) => setEntryDate(event.target.value)}
                  className="mt-1 w-full rounded border border-input bg-background px-3 py-2"
                />
              </label>
              <label className="text-sm">
                Descrizione
                <Input
                  aria-label="Descrizione"
                  type="text"
                  maxLength={300}
                  required
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  className="mt-1 w-full rounded border border-input bg-background px-3 py-2"
                />
              </label>
              <Button
                type="submit"
                disabled={createTimesheet.isPending || updateTimesheet.isPending}
                className="rounded bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
              >
                {createTimesheet.isPending || updateTimesheet.isPending
                  ? "Salvataggio…"
                  : editingTimesheetId
                    ? "Aggiorna"
                    : "Salva"}
              </Button>
              {editingTimesheetId && (
                <Button
                  type="button"
                  onClick={() => {
                    setEditingTimesheetId(null);
                    setTimesheetOpen(false);
                  }}
                  className="rounded border border-border px-4 py-2 text-sm"
                >
                  Annulla
                </Button>
              )}
            </form>
          )}
          {(createTimesheet.isError || updateTimesheet.isError || deleteTimesheet.isError) && (
            <p role="alert" className="text-sm text-destructive">
              Impossibile registrare il consuntivo. Verifica giornate e descrizione.
            </p>
          )}
          {ledger.isError ? (
            <ErrorState
              title="Impossibile caricare i movimenti del progetto"
              action={
                <Button variant="secondary" onClick={() => void ledger.refetch()}>
                  Riprova
                </Button>
              }
            />
          ) : ledger.isLoading ? (
            <LoadingState />
          ) : timesheets.length ? (
            <div className="overflow-x-auto rounded-lg border border-border bg-card">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-left">
                  <tr>
                    <th className="p-3">Data</th>
                    <th className="p-3">Utente</th>
                    <th className="p-3 text-right">Giornate</th>
                    <th className="p-3">Descrizione</th>
                    {canEditTimesheets(session) && <th className="p-3 text-right">Azioni</th>}
                  </tr>
                </thead>
                <tbody>
                  {timesheets.map((entry) => (
                    <tr key={entry.id} className="border-t border-border">
                      <td className="p-3">{entry.data}</td>
                      <td className="p-3">{entry.utente}</td>
                      <td className="p-3 text-right">
                        <DaysValue value={entry.giornate} />
                      </td>
                      <td className="p-3">{entry.descrizione || "—"}</td>
                      {canEditTimesheets(session) && (
                        <td className="p-3 text-right">
                          <div className="flex justify-end gap-2">
                            <Button
                              type="button"
                              onClick={() => {
                                setEditingTimesheetId(entry.id);
                                setDays(entry.giornate);
                                setDescription(entry.descrizione);
                                setEntryDate(entry.data);
                                setTimesheetOpen(true);
                              }}
                              className="rounded border border-border px-2 py-1 text-xs hover:bg-muted"
                            >
                              Modifica
                            </Button>
                            <Button
                              type="button"
                              onClick={() => {
                                if (window.confirm("Eliminare questo consuntivo?")) {
                                  deleteTimesheet.mutate(entry.id);
                                }
                              }}
                              disabled={deleteTimesheet.isPending}
                              className="rounded border border-destructive px-2 py-1 text-xs text-destructive hover:bg-destructive/10 disabled:opacity-50"
                            >
                              Elimina
                            </Button>
                          </div>
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

        <Tabs.Content value="Wallet" className="pt-4">
          {ledger.isError ? (
            <ErrorState
              title="Impossibile caricare i movimenti del progetto"
              action={
                <Button variant="secondary" onClick={() => void ledger.refetch()}>
                  Riprova
                </Button>
              }
            />
          ) : ledger.isLoading ? (
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
                <Input
                  id="planned-end-date"
                  type="date"
                  defaultValue={project.data_fine_prevista ?? ""}
                  className="rounded border border-input bg-background px-3 py-2 text-sm"
                />
                <Button
                  className="rounded bg-accent px-3 py-2 text-sm font-medium text-accent-foreground"
                  onClick={() => {
                    const input = document.getElementById("planned-end-date") as HTMLInputElement;
                    update.mutate({ planned_end_date: input.value });
                  }}
                >
                  Aggiorna data fine prevista
                </Button>
              </div>
            </div>
          ) : (
            <p className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
              Consultazione disponibile; le modifiche non sono consentite per questo progetto.
            </p>
          )}
        </Tabs.Content>

        <Tabs.Content value="Storico modifiche" className="pt-4">
          {audit.isError ? (
            <ErrorState title="Impossibile caricare lo storico del progetto" />
          ) : audit.isLoading ? (
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
