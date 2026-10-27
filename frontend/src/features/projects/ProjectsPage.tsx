import { useCallback, useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { DataTable, type DataTableColumnClasses } from "@/components/DataTable";
import { DaysValue } from "@/components/DaysValue";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorState, LoadingState } from "@/components/UiState";
import { useSession } from "@/features/auth/session";
import { api } from "@/lib/api";
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
  consumato_via_wallet: string;
  consumato_totale: string;
  residuo: string;
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
  codice: { cell: "font-mono" },
  titolo: { header: "min-w-64", cell: "min-w-64 whitespace-normal" },
  budget: { header: "text-right", cell: "text-right tabular-nums" },
  consumato_totale: { header: "text-right", cell: "text-right tabular-nums" },
  residuo: { header: "text-right", cell: "text-right tabular-nums" },
  actions: { header: "text-center", cell: "text-center" },
};

export function ProjectsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { session } = useSession();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
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
        accessorKey: "codice",
        header: "Codice",
        cell: ({ row }) => (
          <span className="font-mono font-medium text-accent">{row.original.codice}</span>
        ),
      },
      { accessorKey: "titolo", header: "Titolo" },
      { accessorKey: "tipo_contratto", header: "Tipo" },
      {
        accessorKey: "budget",
        header: "Budget",
        cell: ({ row }) => (
          <DaysValue value={row.original.budget} suffix={false} label="Budget API" />
        ),
      },
      {
        accessorKey: "consumato_totale",
        header: "Consumato",
        cell: ({ row }) => (
          <DaysValue value={row.original.consumato_totale} suffix={false} label="Consumato API" />
        ),
      },
      {
        accessorKey: "residuo",
        header: "Residuo",
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
                <button
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
                  className="inline-flex items-center justify-center rounded bg-emerald-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
                >
                  Valida chiusura
                </button>
              ) : null}
              {showEdit ? (
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    setEditingProjectId(item.id);
                  }}
                  data-testid={`edit-project-${item.id}`}
                  className="inline-flex items-center justify-center rounded bg-amber-500 px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-slate-950 shadow-sm transition-colors hover:bg-amber-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-500"
                >
                  EDIT
                </button>
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
      (query.data?.results ?? []).filter((project) => {
        const needle = search.toLocaleLowerCase("it");
        return (
          (!needle ||
            `${project.codice} ${project.titolo}`.toLocaleLowerCase("it").includes(needle)) &&
          (!status || (project.stato_operativo ?? project.stato_consuntivazione) === status)
        );
      }),
    [query.data, search, status],
  );

  return (
    <section className="space-y-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Progetti</h1>
          <p className="text-sm text-muted-foreground">
            Budget, consumi e residui calcolati dal ledger.
          </p>
        </div>
        {canCreateProjects(session) && <NewProjectDialog />}
      </header>
      <div className="flex flex-wrap gap-2 rounded-lg border border-border bg-card p-3">
        <label className="flex min-w-64 flex-1 items-center gap-2 rounded-md border border-input px-3">
          <Search className="size-4 text-muted-foreground" aria-hidden />
          <span className="sr-only">Cerca progetti</span>
          <input
            className="h-9 w-full bg-transparent text-sm outline-none"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Codice o titolo"
          />
        </label>
        <select
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
        </select>
        <span className="self-center text-sm text-muted-foreground">
          {filtered.length} risultati
        </span>
      </div>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState
          title="Impossibile caricare i progetti"
          action={
            <button
              className="text-sm font-medium text-accent"
              onClick={() => void query.refetch()}
            >
              Riprova
            </button>
          }
        />
      ) : (
        <DataTable
          data={filtered}
          columns={columns}
          emptyLabel="Nessun progetto corrisponde ai filtri."
          onRowClick={(project) => navigate(`/progetti/${project.id}`)}
          getColumnClasses={getProjectColumnClasses}
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
