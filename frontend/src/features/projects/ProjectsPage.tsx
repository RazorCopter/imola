import { PageHeader, FilterBar } from "@/components/PageHeader";
import { Button, Input, Select } from "@/components/Controls";
import { useCallback, useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { DataTable, type DataTableColumnClasses } from "@/components/DataTable";
import { DaysValue } from "@/components/DaysValue";
import { KpiCard } from "@/components/KpiCard";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorState, LoadingState } from "@/components/UiState";
import { useSession } from "@/features/auth/session";
import { api } from "@/lib/api";
import { formatPercent } from "@/lib/format";
import { canCreateProjects, canEditProjects, canValidateProjectClosure } from "@/lib/permissions";
import { EditProjectDialog } from "./EditProjectDialog";
import { NewProjectDialog } from "./NewProjectDialog";

export interface ProjectBalance {
  id: string;
  version: number;
  codice: string;
  titolo: string;
  tipo_contratto: string;
  budget: string;
  consuntivi_diretti: string;
  allocato_a_wallet: string;
  rimanente_allocato_wallet: string;
  consumato_via_wallet: string;
  consumato_totale: string;
  residuo: string;
  data_inizio: string | null;
  data_fine_prevista: string | null;
  stato_consuntivazione: string;
  stato_operativo: string;
  stato_fatturazione: string;
  stato_offerta: string;
  stato_residuo: string;
  residuo_scade_il: string | null;
  residuo_giorni_alla_scadenza: number | null;
  residuo_motivo: string;
  spiegazione_residuo: string;
  permissions: {
    edit?: boolean;
    annotate?: boolean;
    validate_closure?: boolean;
  };
}

interface ProjectResponse {
  results: ProjectBalance[];
  count: number;
}

const PROJECT_COLUMN_CLASSES: Record<string, DataTableColumnClasses> = {
  titolo: { header: "min-w-64", cell: "min-w-64 max-w-sm whitespace-normal" },
  budget: { header: "text-right", cell: "text-right tabular-nums" },
  consumato_totale: { header: "text-right", cell: "text-right tabular-nums" },
  residuo: { header: "text-right", cell: "text-right tabular-nums" },
  actions: { header: "text-center", cell: "text-center" },
};

function compareDays(a: unknown, b: unknown) {
  const left = typeof a === "string" && a.trim() ? Number(a) : NaN;
  const right = typeof b === "string" && b.trim() ? Number(b) : NaN;
  if (!Number.isFinite(left)) return Number.isFinite(right) ? 1 : 0;
  if (!Number.isFinite(right)) return -1;
  return left - right;
}

export function ProjectsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { session } = useSession();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [order, setOrder] = useState("original");
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);

  const canGlobalEdit = canEditProjects(session);
  const canValidateClosure = canValidateProjectClosure(session);
  const validateClosure = useMutation({
    mutationFn: (project: ProjectBalance) =>
      api.post(`/projects/${project.id}/validate-closure`, {
        expected_version: project.version,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["projects", "balances"] });
    },
  });
  const getProjectColumnClasses = useCallback(
    (columnId: string) => PROJECT_COLUMN_CLASSES[columnId],
    [],
  );

  const columns = useMemo<ColumnDef<ProjectBalance>[]>(
    () => [
      {
        accessorKey: "titolo",
        header: "Progetto",
        cell: ({ row }) => (
          <div className="max-w-sm py-1">
            <div
              className="line-clamp-2 font-semibold leading-snug text-foreground"
              title={row.original.titolo}
            >
              {row.original.titolo || "Titolo non disponibile"}
            </div>
            <div
              className="mt-1 break-all text-xs text-muted-foreground"
              title={row.original.codice}
            >
              {row.original.codice}
            </div>
          </div>
        ),
      },
      { accessorKey: "tipo_contratto", header: "Tipo" },
      {
        accessorKey: "budget",
        header: "Budget",
        sortingFn: (a, b) => compareDays(a.original.budget, b.original.budget),
        cell: ({ row }) => (
          <DaysValue value={row.original.budget} suffix={false} label="Budget API" />
        ),
      },
      {
        accessorKey: "consumato_totale",
        header: "Consumato",
        sortingFn: (a, b) => compareDays(a.original.consumato_totale, b.original.consumato_totale),
        cell: ({ row }) => {
          const budget = Number(row.original.budget);
          const consumed = Number(row.original.consumato_totale);
          const valid =
            typeof row.original.budget === "string" &&
            row.original.budget.trim() !== "" &&
            typeof row.original.consumato_totale === "string" &&
            row.original.consumato_totale.trim() !== "" &&
            Number.isFinite(budget) &&
            Number.isFinite(consumed) &&
            budget > 0 &&
            consumed >= 0;
          const ratio = valid ? (consumed / budget) * 100 : null;
          return (
            <div className="ml-auto min-w-24">
              <DaysValue
                value={row.original.consumato_totale}
                suffix={false}
                label="Consumato API"
              />
              {ratio !== null && (
                <div className="mt-1.5">
                  <div className="h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                    <div
                      className={
                        ratio > 100
                          ? "h-full rounded-full bg-danger"
                          : "h-full rounded-full bg-accent"
                      }
                      style={{ width: `${Math.min(ratio, 100)}%` }}
                    />
                  </div>
                  <span className="mt-1 block text-[11px] text-muted-foreground">
                    {ratio.toLocaleString("it-IT", { maximumFractionDigits: 1 })}% del budget
                  </span>
                </div>
              )}
            </div>
          );
        },
      },
      {
        accessorKey: "residuo",
        header: "Residuo",
        sortingFn: (a, b) => compareDays(a.original.residuo, b.original.residuo),
        cell: ({ row }) => (
          <DaysValue
            value={row.original.residuo}
            suffix={false}
            label={row.original.spiegazione_residuo}
          />
        ),
      },
      {
        accessorKey: "stato_operativo",
        header: "Stato",
        cell: ({ row }) => (
          <StatusBadge
            status={row.original.stato_operativo ?? row.original.stato_consuntivazione}
          />
        ),
      },
      {
        accessorKey: "stato_fatturazione",
        header: "Fatturazione",
        cell: ({ row }) => (
          <StatusBadge status={row.original.stato_fatturazione} domain="billing" />
        ),
      },
      {
        id: "actions",
        header: "Azioni",
        cell: ({ row }) => {
          const item = row.original;
          const showEdit = canGlobalEdit || item.permissions?.edit || item.permissions?.annotate;
          const showValidate =
            item.stato_operativo === "CHIUSURA_DA_VALIDARE" &&
            canValidateClosure &&
            item.permissions?.validate_closure;
          if (!showEdit && !showValidate) return null;

          return (
            <div className="flex items-center justify-center gap-2">
              {showValidate ? (
                <Button
                  type="button"
                  disabled={validateClosure.isPending}
                  onClick={(event) => {
                    event.stopPropagation();
                    if (
                      window.confirm(
                        "Confermi di avere chiuso il progetto anche sul gestionale del fornitore?",
                      )
                    ) {
                      validateClosure.mutate(item);
                    }
                  }}
                  data-testid={`validate-closure-${item.id}`}
                  className="inline-flex items-center justify-center rounded bg-emerald-700 px-2.5 py-1 text-xs font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"
                >
                  Valida chiusura
                </Button>
              ) : null}
              {showEdit ? (
                <Button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    setEditingProjectId(item.id);
                  }}
                  data-testid={`edit-project-${item.id}`}
                  className="inline-flex items-center justify-center rounded bg-amber-500 px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-slate-950 shadow-sm transition-colors hover:bg-amber-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-500"
                >
                  EDIT
                </Button>
              ) : null}
            </div>
          );
        },
      },
    ],
    [canGlobalEdit, canValidateClosure, validateClosure],
  );
  const query = useQuery({
    queryKey: ["projects", "balances"],
    queryFn: () => api.get<ProjectResponse>("/projects/balances"),
  });
  const filtered = useMemo(
    () =>
      (query.data?.results ?? [])
        .filter((project) => {
          const needle = search.toLocaleLowerCase("it");
          return (
            (!needle ||
              `${project.codice} ${project.titolo}`.toLocaleLowerCase("it").includes(needle)) &&
            (!status || (project.stato_operativo ?? project.stato_consuntivazione) === status)
          );
        })
        .sort((a, b) =>
          order === "code"
            ? a.codice.localeCompare(b.codice, "it")
            : order === "title"
              ? a.titolo.localeCompare(b.titolo, "it")
              : 0,
        ),
    [query.data, search, status, order],
  );

  /**
   * Indicatori di portafoglio: deliberatamente su tutti i progetti e non sul sottoinsieme
   * filtrato, come il canone e il wallet. La tabella ha il suo contatore di risultati.
   */
  const kpi = useMemo(() => {
    const all = query.data?.results ?? [];
    const sum = (rows: ProjectBalance[], field: keyof ProjectBalance) =>
      rows.reduce((total, row) => total + Number(row[field] ?? 0), 0);
    const stato = (row: ProjectBalance) => row.stato_operativo ?? row.stato_consuntivazione;
    const inCorso = all.filter((row) => stato(row) !== "CHIUSO");
    const daValidare = all.filter((row) => stato(row) === "CHIUSURA_DA_VALIDARE");
    const aRischio = all.filter((row) =>
      ["IN_SCADENZA", "SCADUTO"].includes(row.stato_residuo ?? ""),
    );
    const budget = sum(inCorso, "budget");
    const consumato = sum(inCorso, "consumato_totale");
    return {
      totale: all.length,
      inCorso: inCorso.length,
      budget,
      consumato,
      percentuale: budget > 0 ? (consumato / budget) * 100 : null,
      // Residui e sforamenti restano distinti, come nel bilancio del wallet: sommarli
      // insieme farebbe sparire uno sforamento dentro il residuo di un altro progetto.
      residuo: inCorso.reduce((total, row) => total + Math.max(0, Number(row.residuo ?? 0)), 0),
      sforamento: inCorso.reduce((total, row) => total + Math.min(0, Number(row.residuo ?? 0)), 0),
      progettiSforati: inCorso.filter((row) => Number(row.residuo ?? 0) < 0).length,
      daValidare: daValidare.length,
      aRischioGiornate: sum(aRischio, "residuo"),
      aRischioProgetti: aRischio.length,
    };
  }, [query.data]);

  return (
    <section className="space-y-4">
      <PageHeader
        eyebrow="Gestione · Portafoglio"
        title="Progetti"
        description="Budget, consumi e residui calcolati dal ledger."
        actions={<>{canCreateProjects(session) && <NewProjectDialog />}</>}
      />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        <KpiCard
          label="Progetti in corso"
          value={kpi.inCorso}
          hint={`su ${kpi.totale} in portafoglio`}
          tooltip="Progetti non ancora chiusi. Il totale comprende anche i chiusi, indipendentemente dai filtri della tabella."
        />
        <KpiCard
          label="Budget in corso"
          value={<DaysValue value={kpi.budget} />}
          hint="Monte giornate dei progetti non chiusi"
          tooltip="Somma del budget dei progetti non ancora chiusi: le giornate su cui si sta ancora lavorando."
        />
        <KpiCard
          label="Consumato"
          value={<DaysValue value={kpi.consumato} />}
          hint={
            kpi.percentuale === null
              ? "Nessun budget in corso"
              : `${formatPercent(kpi.percentuale)} sul budget in corso`
          }
          tooltip="Consuntivi diretti più giornate erose tramite wallet, sui progetti non chiusi."
        />
        <KpiCard
          label="Residuo da spendere"
          value={<DaysValue value={kpi.residuo} />}
          tone={kpi.progettiSforati > 0 ? "warn" : "ok"}
          hint={
            kpi.progettiSforati > 0 ? (
              <>
                e <DaysValue value={Math.abs(kpi.sforamento)} /> di sforamento su{" "}
                {kpi.progettiSforati} progetti
              </>
            ) : (
              "Budget meno consuntivi e quote già allocate"
            )
          }
          tooltip="Giornate ancora disponibili sui progetti non chiusi: budget meno consuntivi diretti meno quote allocate al wallet. Gli sforamenti sono contati a parte, per non compensarsi con i residui altrui."
        />
        <KpiCard
          label="Residui a rischio"
          value={<DaysValue value={kpi.aRischioGiornate} />}
          tone={kpi.aRischioGiornate > 0 ? "warn" : "neutral"}
          hint={
            kpi.daValidare > 0
              ? `${kpi.aRischioProgetti} progetti · ${kpi.daValidare} chiusure da validare`
              : `${kpi.aRischioProgetti} progetti in scadenza o scaduti`
          }
          tooltip="Giornate residue di progetti il cui residuo è in scadenza o già scaduto: vanno spese o conferite al wallet prima del termine."
        />
      </div>
      <FilterBar>
        <label className="flex min-w-64 flex-1 items-center gap-2 rounded-md border border-input px-3">
          <Search className="size-4 text-muted-foreground" aria-hidden />
          <span className="sr-only">Cerca progetti</span>
          <Input
            className="h-9 w-full border-0 bg-transparent px-0 text-sm outline-none"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Codice o titolo"
          />
        </label>
        <Select
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          aria-label="Filtra stato operativo"
        >
          <option value="">Tutti gli stati</option>
          <option value="CANONE">Canone</option>
          <option value="WALLET">Wallet</option>
          <option value="IN_CORSO">In corso</option>
          <option value="OFFERTA_ACCETTATA">Offerta accettata</option>
          <option value="OFFERTA_INVIATA">Offerta inviata</option>
          <option value="CHIUSURA_DA_VALIDARE">Chiusura da validare</option>
          <option value="CHIUSO">Chiuso</option>
          <option value="DA_VERIFICARE">Da verificare</option>
        </Select>
        <Select
          aria-label="Ordina progetti"
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          value={order}
          onChange={(event) => setOrder(event.target.value)}
        >
          <option value="original">Ordine originale</option>
          <option value="title">Titolo A–Z</option>
          <option value="code">Codice A–Z</option>
        </Select>
        <span className="self-center text-sm text-muted-foreground">
          {filtered.length} risultati
        </span>
        {(search || status) && (
          <Button
            type="button"
            className="rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
            onClick={() => {
              setSearch("");
              setStatus("");
            }}
          >
            Azzera filtri
          </Button>
        )}
      </FilterBar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState
          title="Impossibile caricare i progetti"
          action={
            <Button
              className="text-sm font-medium text-accent"
              onClick={() => void query.refetch()}
            >
              Riprova
            </Button>
          }
        />
      ) : (
        <DataTable
          key={order}
          data={filtered}
          columns={columns}
          emptyLabel="Nessun progetto corrisponde ai filtri."
          onRowClick={(project) => navigate(`/progetti/${project.id}`)}
          getColumnClasses={getProjectColumnClasses}
          fitWidth
          rowHeight={72}
        />
      )}

      {editingProjectId && (
        <EditProjectDialog
          projectId={editingProjectId}
          open={Boolean(editingProjectId)}
          onOpenChange={(open) => {
            if (!open) setEditingProjectId(null);
          }}
          onDeleted={(projectId) => {
            queryClient.setQueryData<ProjectResponse>(["projects", "balances"], (current) =>
              current
                ? {
                    ...current,
                    count: Math.max(0, current.count - 1),
                    results: current.results.filter((project) => project.id !== projectId),
                  }
                : current,
            );
            setEditingProjectId(null);
          }}
        />
      )}
    </section>
  );
}
