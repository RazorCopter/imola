import { PageHeader } from "@/components/PageHeader";
import { Button, Input, Select } from "@/components/Controls";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/UiState";
import { ResizableTableHeader } from "@/components/ResizableTableHeader";
import { useSession } from "@/features/auth/session";
import { api } from "@/lib/api";
import { canWriteLedger } from "@/lib/permissions";

interface ReviewProject {
  id: string;
  codice: string;
  titolo: string;
  stato_consuntivazione: string;
  data_chiusura: string | null;
  data_fine_prevista: string | null;
  motivo_revisione: string;
}

export function ReviewQueuePage() {
  const client = useQueryClient();
  const { session } = useSession();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<string>("CHIUSO");
  const [closureDate, setClosureDate] = useState<string>("");

  const query = useQuery({
    queryKey: ["review-queue"],
    queryFn: () => api.get<{ count: number; results: ReviewProject[] }>("/review-queue"),
  });

  const confirm = useMutation({
    mutationFn: ({
      id,
      timesheet_status,
      actual_closure_date,
    }: {
      id: string;
      timesheet_status: string;
      actual_closure_date: string;
    }) =>
      api.post(`/projects/${id}/confirm-review`, {
        timesheet_status,
        actual_closure_date,
      }),
    onSuccess: async () => {
      setSelectedId(null);
      await client.invalidateQueries({ queryKey: ["review-queue"] });
      await client.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError || !query.data)
    return <ErrorState title="Impossibile caricare la coda di revisione" />;

  const projects = query.data.results.filter((project) =>
    `${project.codice} ${project.titolo} ${project.motivo_revisione}`
      .toLocaleLowerCase("it")
      .includes(search.trim().toLocaleLowerCase("it")),
  );

  return (
    <section className="space-y-5">
      <PageHeader
        eyebrow="Controllo · Verifiche"
        title="Coda di revisione progetti"
        description={
          <>
            {query.data.count} progetti richiedono conferma formale dello stato di consuntivazione o
            della data di chiusura.
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card p-3">
        <label className="min-w-0 flex-1 text-sm">
          <span className="sr-only">Cerca nella coda di revisione</span>
          <Input
            type="search"
            aria-label="Cerca nella coda di revisione"
            className="h-9 w-full rounded-md border border-input bg-background px-3"
            placeholder="Codice, titolo o motivazione"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <span className="text-sm text-muted-foreground">{projects.length} risultati</span>
      </div>

      {confirm.isError && (
        <p
          role="alert"
          className="rounded-lg border border-danger/30 bg-danger-subtle p-3 text-sm text-danger"
        >
          Impossibile salvare la revisione. Riprova.
        </p>
      )}
      {projects.length === 0 ? (
        <EmptyState
          title={
            search ? "Nessun progetto corrisponde alla ricerca" : "Nessun progetto in revisione"
          }
          detail={
            search
              ? "Modifica il testo di ricerca per vedere altri risultati."
              : "Le verifiche da completare compariranno qui."
          }
        />
      ) : (
        <div className="overflow-auto rounded-lg border border-border bg-card">
          <table className="w-full table-fixed text-sm">
            <thead className="bg-muted text-left text-xs uppercase text-muted-foreground">
              <tr>
                <ResizableTableHeader initialWidth={220}>Progetto</ResizableTableHeader>
                <ResizableTableHeader initialWidth={110}>Stato attuale</ResizableTableHeader>
                <ResizableTableHeader initialWidth={150}>
                  Data prevista / chiusura
                </ResizableTableHeader>
                <ResizableTableHeader initialWidth={190}>Azione</ResizableTableHeader>
              </tr>
            </thead>
            <tbody>
              {projects.map((p) => (
                <tr key={p.id} className="border-t border-border">
                  <td className="max-w-sm truncate p-3" title={p.titolo}>
                    {p.titolo}
                    <span
                      className="block truncate text-xs font-medium text-muted-foreground"
                      title={p.codice}
                    >
                      {p.codice}
                    </span>
                    <span
                      className="block truncate text-xs font-normal text-muted-foreground"
                      title={p.motivo_revisione}
                    >
                      {p.motivo_revisione}
                    </span>
                  </td>
                  <td className="p-3">{p.stato_consuntivazione}</td>
                  <td className="p-3 text-xs text-muted-foreground">
                    {p.data_chiusura ?? p.data_fine_prevista ?? "-"}
                  </td>
                  <td className="p-3">
                    {!canWriteLedger(session) ? (
                      <span className="text-xs text-muted-foreground">Sola lettura</span>
                    ) : selectedId === p.id ? (
                      <div className="flex flex-wrap items-center gap-2">
                        <Select
                          aria-label={`Stato per ${p.codice}`}
                          value={status}
                          onChange={(e) => setStatus(e.target.value)}
                          className="rounded border border-input bg-background px-2 py-1 text-xs"
                        >
                          <option value="CHIUSO">CHIUSO</option>
                          <option value="ATTIVO">ATTIVO</option>
                        </Select>
                        <Input
                          aria-label={`Data chiusura per ${p.codice}`}
                          type="date"
                          value={closureDate}
                          onChange={(e) => setClosureDate(e.target.value)}
                          className="rounded border border-input bg-background px-2 py-1 text-xs"
                        />
                        <Button
                          disabled={confirm.isPending || !closureDate}
                          className="rounded bg-accent px-2 py-1 text-xs font-medium text-accent-foreground"
                          onClick={() =>
                            confirm.mutate({
                              id: p.id,
                              timesheet_status: status,
                              actual_closure_date: closureDate,
                            })
                          }
                        >
                          Salva
                        </Button>
                        <Button
                          className="text-xs text-muted-foreground hover:underline"
                          onClick={() => setSelectedId(null)}
                        >
                          Annulla
                        </Button>
                      </div>
                    ) : (
                      <Button
                        className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-xs hover:bg-muted"
                        onClick={() => {
                          setSelectedId(p.id);
                          setStatus(p.stato_consuntivazione === "CHIUSO" ? "CHIUSO" : "ATTIVO");
                          setClosureDate(p.data_chiusura ?? p.data_fine_prevista ?? "");
                        }}
                      >
                        <CheckCircle2 className="size-3.5" />
                        Conferma revisione
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
