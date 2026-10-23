import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { DataTable } from "@/components/DataTable";
import { DaysValue } from "@/components/DaysValue";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorState, LoadingState } from "@/components/UiState";
import { useSession } from "@/features/auth/session";
import { api } from "@/lib/api";
import { canCreateProjects, canEditProjects } from "@/lib/permissions";
import { EditProjectDialog } from "./EditProjectDialog";
import { NewProjectDialog } from "./NewProjectDialog";

export interface ProjectBalance {
  id: string;
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
  };
}

interface ProjectResponse {
  results: ProjectBalance[];
  count: number;
}

export function ProjectsPage() {
  const navigate = useNavigate();
  const { session } = useSession();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);

  const canGlobalEdit = canEditProjects(session);

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
        accessorKey: "stato_consuntivazione",
        header: "Consuntivazione",
        cell: ({ row }) => (
          <StatusBadge status={row.original.stato_consuntivazione} domain="timesheet" />
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
          if (!showEdit) return null;

          return (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setEditingProjectId(item.id);
              }}
              data-testid={`edit-project-${item.id}`}
              className="inline-flex items-center justify-center rounded bg-amber-500 px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-slate-950 shadow-sm transition-colors hover:bg-amber-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-500"
            >
              EDIT
            </button>
          );
        },
      },
    ],
    [canGlobalEdit],
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
          (!status || project.stato_consuntivazione === status)
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
          aria-label="Filtra stato consuntivazione"
        >
          <option value="">Tutti gli stati</option>
          <option value="NON_AVVIATO">Non avviato</option>
          <option value="ATTIVO">Attivo</option>
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
        />
      )}

      {editingProjectId && (
        <EditProjectDialog
          projectId={editingProjectId}
          open={Boolean(editingProjectId)}
          onOpenChange={(open) => {
            if (!open) setEditingProjectId(null);
          }}
        />
      )}
    </section>
  );
}
