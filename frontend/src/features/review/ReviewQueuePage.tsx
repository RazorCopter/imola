import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { useState } from "react";

import { ErrorState, LoadingState } from "@/components/UiState";
import { api } from "@/lib/api";

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
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("CHIUSO");
  const [closureDate, setClosureDate] = useState<string>("2026-06-30");

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

  const projects = query.data.results;

  return (
    <section className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold">Coda di revisione progetti</h1>
        <p className="text-sm text-muted-foreground">
          {query.data.count} progetti richiedono conferma formale dello stato di consuntivazione o
          della data di chiusura.
        </p>
      </header>

      <div className="overflow-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="bg-muted text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="p-3">Codice</th>
              <th className="p-3">Titolo</th>
              <th className="p-3">Stato attuale</th>
              <th className="p-3">Data prevista / chiusura</th>
              <th className="p-3">Azione</th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.id} className="border-t border-border">
                <td className="p-3 font-mono font-medium">{p.codice.split("-")[0]}</td>
                <td className="max-w-sm truncate p-3">{p.titolo}</td>
                <td className="p-3">{p.stato_consuntivazione}</td>
                <td className="p-3 text-xs text-muted-foreground">
                  {p.data_chiusura ?? p.data_fine_prevista ?? "-"}
                </td>
                <td className="p-3">
                  {selectedId === p.id ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <select
                        value={status}
                        onChange={(e) => setStatus(e.target.value)}
                        className="rounded border border-input bg-background px-2 py-1 text-xs"
                      >
                        <option value="CHIUSO">CHIUSO</option>
                        <option value="ATTIVO">ATTIVO</option>
                      </select>
                      <input
                        type="date"
                        value={closureDate}
                        onChange={(e) => setClosureDate(e.target.value)}
                        className="rounded border border-input bg-background px-2 py-1 text-xs"
                      />
                      <button
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
                      </button>
                      <button
                        className="text-xs text-muted-foreground hover:underline"
                        onClick={() => setSelectedId(null)}
                      >
                        Annulla
                      </button>
                    </div>
                  ) : (
                    <button
                      className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-xs hover:bg-muted"
                      onClick={() => {
                        setSelectedId(p.id);
                        setStatus(p.stato_consuntivazione === "CHIUSO" ? "CHIUSO" : "ATTIVO");
                        setClosureDate(p.data_chiusura ?? "2026-06-30");
                      }}
                    >
                      <CheckCircle2 className="size-3.5" />
                      Conferma revisione
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
