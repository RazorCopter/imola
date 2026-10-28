import { Button, Input, Select } from "@/components/Controls";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Play } from "lucide-react";
import { useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/UiState";
import { useSession } from "@/features/auth/session";
import { api } from "@/lib/api";
import { canWriteLedger } from "@/lib/permissions";

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
  const { session } = useSession();
  const [status, setStatus] = useState("APERTA");
  const [acceptingId, setAcceptingId] = useState<string | null>(null);
  const [exceptionDate, setExceptionDate] = useState("");
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
    onSuccess: async () => {
      setAcceptingId(null);
      setExceptionDate("");
      await client.invalidateQueries({ queryKey: ["anomalies"] });
    },
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState title="Impossibile caricare le anomalie" />;
  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-6">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-accent">
            Controllo · Eccezioni
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">Inbox anomalie</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Rilievi automatici deduplicati e anomalie seed storicizzate.
          </p>
        </div>
        {canWriteLedger(session) && (
          <Button
            className="flex items-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-foreground"
            onClick={() => run.mutate()}
            disabled={run.isPending}
          >
            <Play className="size-4" />
            Esegui controlli
          </Button>
        )}
      </header>
      <div className="flex flex-wrap gap-3 rounded-xl border border-border bg-card p-3">
        <Select
          aria-label="Filtra anomalie per stato"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
        >
          <option value="">Tutti gli stati</option>
          <option value="APERTA">Aperte</option>
          <option value="IN_VERIFICA">In verifica</option>
          <option value="RISOLTA">Risolte</option>
          <option value="ACCETTATA">Accettate</option>
        </Select>
        <span className="self-center text-sm text-muted-foreground">
          {query.data?.results.length ?? 0} elementi
        </span>
      </div>
      {(run.isError || act.isError) && (
        <p
          role="alert"
          className="rounded-lg border border-danger/30 bg-danger-subtle p-3 text-sm text-danger"
        >
          Operazione non riuscita. Riprova.
        </p>
      )}
      {query.data?.results.length === 0 && (
        <EmptyState
          title="Nessuna anomalia trovata"
          detail="Non ci sono anomalie per lo stato selezionato."
        />
      )}
      <div className="space-y-3">
        {query.data?.results.map((item) => (
          <article
            key={item.id}
            className="rounded-xl border border-border bg-card p-5 shadow-subtle"
          >
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
              {canWriteLedger(session) && item.stato === "APERTA" && (
                <div className="flex gap-2">
                  <Button
                    className="rounded border border-border px-2 py-1 text-xs"
                    onClick={() => act.mutate({ id: item.id, action: "take" })}
                  >
                    Prendi in carico
                  </Button>
                  <Button
                    className="rounded border border-ok/40 px-2 py-1 text-xs text-ok"
                    onClick={() =>
                      act.mutate({ id: item.id, action: "resolve", nota: "Verificata e risolta" })
                    }
                  >
                    Risolvi
                  </Button>
                  <Button
                    className="rounded border border-accent/40 px-2 py-1 text-xs text-accent"
                    onClick={() => {
                      setAcceptingId(item.id);
                      setExceptionDate("");
                    }}
                  >
                    Accetta con deroga
                  </Button>
                </div>
              )}
            </div>
            {acceptingId === item.id && (
              <div className="mt-3 flex flex-wrap items-end gap-2 rounded-lg border border-border bg-muted/30 p-3">
                <label className="text-sm">
                  Scadenza deroga
                  <Input
                    aria-label="Scadenza deroga"
                    type="date"
                    value={exceptionDate}
                    onChange={(event) => setExceptionDate(event.target.value)}
                    className="mt-1 block rounded-md border border-input bg-background px-3 py-2"
                  />
                </label>
                <Button
                  className="rounded border border-accent px-3 py-2 text-sm text-accent disabled:opacity-50"
                  disabled={!exceptionDate || act.isPending}
                  onClick={() =>
                    act.mutate({
                      id: item.id,
                      action: "accept",
                      nota: "Deroga approvata con scadenza",
                      finoAl: exceptionDate,
                    })
                  }
                >
                  Conferma deroga
                </Button>
                <Button
                  className="rounded border border-border px-3 py-2 text-sm"
                  onClick={() => setAcceptingId(null)}
                >
                  Annulla
                </Button>
              </div>
            )}
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
