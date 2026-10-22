import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Tabs from "@radix-ui/react-tabs";
import { Link, useParams } from "react-router-dom";

import { DaysValue } from "@/components/DaysValue";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/UiState";
import { api } from "@/lib/api";
import type { ProjectBalance } from "./ProjectsPage";

interface ProjectResponse {
  results: ProjectBalance[];
}

export function ProjectDetailPage() {
  const { projectId } = useParams();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["projects", "balances"],
    queryFn: () => api.get<ProjectResponse>("/projects/balances"),
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
    mutationFn: (payload: { planned_end_date?: string; notes?: string }) =>
      api.patch(`/projects/${projectId}`, payload),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["projects"] });
      await client.invalidateQueries({ queryKey: ["audit", "project", projectId] });
    },
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState title="Impossibile caricare il progetto" />;
  const project = query.data?.results.find((item) => item.id === projectId);
  if (!project) return <EmptyState title="Progetto non trovato" />;
  const canAnnotate = project.permissions.annotate;

  const metrics = [
    ["Budget", project.budget],
    ["Consuntivi diretti", project.consuntivi_diretti],
    ["Allocato al wallet", project.allocato_a_wallet],
    ["Consumato via wallet", project.consumato_via_wallet],
    ["Consumato totale", project.consumato_totale],
    ["Residuo", project.residuo],
  ] as const;
  const tabs = [
    "Panoramica",
    "Consuntivi",
    "Wallet",
    "Milestone",
    "Residuo",
    "Anomalie",
    "Documenti",
    "Storico modifiche",
  ];

  return (
    <section className="space-y-5">
      <header>
        <Link to="/progetti" className="text-sm text-accent">
          ← Progetti
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-xl font-semibold">{project.codice}</h1>
          <StatusBadge status={project.stato_consuntivazione} domain="timesheet" />
          <StatusBadge status={project.stato_fatturazione} domain="billing" />
          <StatusBadge status={project.stato_offerta} domain="offer" />
        </div>
        <p className="mt-1 text-muted-foreground">{project.titolo}</p>
      </header>
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
        <Tabs.Content value="Panoramica" className="pt-4">
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
          <div className="mt-4 rounded-lg border border-border bg-card p-4">
            <h2 className="font-medium">Validità residuo</h2>
            <div className="mt-2 flex items-center gap-3">
              <StatusBadge status={project.stato_residuo} />
              <span className="text-sm text-muted-foreground">{project.residuo_motivo}</span>
            </div>
            <p className="mt-2 text-xs text-muted-foreground" title={project.spiegazione_residuo}>
              {project.spiegazione_residuo}
            </p>
          </div>
        </Tabs.Content>
        {tabs.slice(1, -1).map((tab) => (
          <Tabs.Content key={tab} value={tab} className="pt-4">
            {tab === "Anomalie" ? (
              canAnnotate ? (
                <div className="rounded-lg border border-border bg-card p-4">
                  <h2 className="font-medium">Azioni sul progetto</h2>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <input
                      id="planned-end-date"
                      type="date"
                      defaultValue="2026-12-31"
                      className="rounded border border-input bg-background px-3 py-2 text-sm"
                    />
                    <button
                      className="rounded bg-accent px-3 py-2 text-sm font-medium text-accent-foreground"
                      onClick={() => {
                        const input = document.getElementById(
                          "planned-end-date",
                        ) as HTMLInputElement;
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
              )
            ) : (
              <EmptyState
                title={`${tab}: nessun elemento da mostrare`}
                detail="La struttura è pronta; i dati specifici saranno collegati ai rispettivi endpoint CRUD."
              />
            )}
          </Tabs.Content>
        ))}
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
                    {record.modifiche.map((m) => (
                      <li key={m}>{m}</li>
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
