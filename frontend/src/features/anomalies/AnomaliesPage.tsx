import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Play } from "lucide-react";
import { useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { ErrorState, LoadingState } from "@/components/UiState";
import { api } from "@/lib/api";

interface Anomaly {
  id: string;
  external_ref: string;
  codice_regola: string;
  severita: string;
  ambito: string;
  descrizione: string;
  stato: string;
  progetto: string | null;
  contesto: Record<string, unknown>;
  azione_suggerita: string;
  nota_risoluzione: string;
  sostituita_da: string | null;
}

export function AnomaliesPage() {
  const client = useQueryClient();
  const [status, setStatus] = useState("APERTA");
  const query = useQuery({
    queryKey: ["anomalies", status],
    queryFn: () => api.get<{ results: Anomaly[] }>(`/anomalies${status ? `?stato=${status}` : ""}`),
  });
  const run = useMutation({
    mutationFn: () => api.post("/checks/run", {}),
    onSuccess: async () => client.invalidateQueries({ queryKey: ["anomalies"] }),
  });
  const act = useMutation({
    mutationFn: ({
      id,
      action,
      nota,
      finoAl,
    }: {
      id: string;
      action: string;
      nota?: string;
      finoAl?: string;
    }) =>
      api.post(`/anomalies/${id}/${action}`, {
        nota: nota ?? "Gestita dall'inbox",
        fino_al: finoAl,
      }),
    onSuccess: async () => client.invalidateQueries({ queryKey: ["anomalies"] }),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState title="Impossibile caricare le anomalie" />;
  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Inbox anomalie</h1>
          <p className="text-sm text-muted-foreground">
            Rilievi automatici deduplicati e anomalie seed storicizzate.
          </p>
        </div>
        <button
          className="flex items-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-foreground"
          onClick={() => run.mutate()}
          disabled={run.isPending}
        >
          <Play className="size-4" />
          Esegui controlli
        </button>
      </header>
      <div className="flex gap-2">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
        >
          <option value="">Tutti gli stati</option>
          <option value="APERTA">Aperte</option>
          <option value="IN_VERIFICA">In verifica</option>
          <option value="RISOLTA">Risolte</option>
          <option value="ACCETTATA">Accettate</option>
        </select>
        <span className="self-center text-sm text-muted-foreground">
          {query.data?.results.length ?? 0} elementi
        </span>
      </div>
      <div className="space-y-3">
        {query.data?.results.map((item) => (
          <article key={item.id} className="rounded-lg border border-border bg-card p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="flex gap-3">
                <AlertTriangle
                  className={
                    item.severita === "ALTA"
                      ? "size-5 text-danger"
                      : item.severita === "MEDIA"
                        ? "size-5 text-warn"
                        : "size-5 text-muted-foreground"
                  }
                />
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-sm font-semibold">
                      {item.external_ref || item.codice_regola}
                    </span>
                    <span className="rounded bg-muted px-2 py-0.5 text-xs">{item.severita}</span>
                    <StatusBadge status={item.stato} />
                  </div>
                  <p className="mt-2 text-sm">{item.descrizione}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {item.progetto ?? item.ambito}
                    {item.sostituita_da ? ` · sostituita da ${item.sostituita_da}` : ""}
                  </p>
                </div>
              </div>
              {item.stato === "APERTA" && (
                <div className="flex gap-2">
                  <button
                    className="rounded border border-border px-2 py-1 text-xs"
                    onClick={() => act.mutate({ id: item.id, action: "take" })}
                  >
                    Prendi in carico
                  </button>
                  <button
                    className="rounded border border-ok/40 px-2 py-1 text-xs text-ok"
                    onClick={() =>
                      act.mutate({ id: item.id, action: "resolve", nota: "Verificata e risolta" })
                    }
                  >
                    Risolvi
                  </button>
                  <button
                    className="rounded border border-accent/40 px-2 py-1 text-xs text-accent"
                    onClick={() =>
                      act.mutate({
                        id: item.id,
                        action: "accept",
                        nota: "Deroga approvata con scadenza",
                        finoAl: "2026-12-31",
                      })
                    }
                  >
                    Accetta con deroga
                  </button>
                </div>
              )}
            </div>
            {item.azione_suggerita && (
              <p className="mt-3 rounded bg-muted p-2 text-xs">
                <strong>Azione:</strong> {item.azione_suggerita}
              </p>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
