/**
 * Riconciliazione: registro delle associazioni fra i valori dell'Excel e le voci
 * dell'applicativo.
 *
 * Non è la vecchia quadratura PPM, rimossa: qui si associa un testo dell'estratto a una
 * destinazione censita, e l'associazione vale anche per le settimane successive, così lo
 * stesso valore non torna a chiedere.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/Controls";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/UiState";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

const TIPI = [
  { id: "TUTTI", label: "Tutte" },
  { id: "PROGETTO", label: "Progetti" },
  { id: "WALLET_ALLOCATION", label: "Wallet" },
  { id: "CANONE_SUBACTIVITY", label: "Organico allargato" },
  { id: "COLLABORATORE", label: "Collaboratori" },
] as const;

interface Associazione {
  id: string;
  tipo: string;
  tipo_etichetta: string;
  valore: string;
  destinazione: string;
  anno: number | null;
  semestre: string;
  confermata_da: string | null;
  confermata_il: string;
}

export function RiconciliazionePage() {
  const client = useQueryClient();
  const [tipo, setTipo] = useState<string>("TUTTI");
  const [errore, setErrore] = useState<string | null>(null);

  const associazioni = useQuery({
    queryKey: ["associazioni", tipo],
    queryFn: () =>
      api.get<{ associazioni: Associazione[] }>(
        tipo === "TUTTI" ? "/imports/mappings" : `/imports/mappings?tipo=${tipo}`,
      ),
  });

  const elimina = useMutation({
    mutationFn: (id: string) => api.delete<void>(`/imports/mappings/${id}`),
    onSuccess: () => {
      setErrore(null);
      void client.invalidateQueries({ queryKey: ["associazioni"] });
    },
    onError: (err) =>
      setErrore(err instanceof ApiError ? err.message : "Eliminazione non riuscita."),
  });

  const righe = associazioni.data?.associazioni ?? [];

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Consuntivi"
        title="Riconciliazione"
        description="Associa i valori dell'estratto Excel alle voci censite nell'applicativo. Ogni associazione confermata vale anche per le settimane successive."
      />

      <div className="flex flex-wrap gap-2">
        {TIPI.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTipo(t.id)}
            className={cn(
              "rounded-md border px-3 py-1.5 text-sm",
              tipo === t.id ? "border-accent bg-accent text-accent-foreground" : "border-input",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {errore ? (
        <div className="rounded-lg border border-danger/30 bg-danger-subtle p-3 text-sm text-danger">
          {errore}
        </div>
      ) : null}

      <div className="rounded-xl border border-border bg-card p-5 shadow-subtle">
        {associazioni.isLoading ? (
          <LoadingState rows={3} />
        ) : associazioni.isError ? (
          <ErrorState title="Associazioni non disponibili" />
        ) : righe.length === 0 ? (
          <EmptyState
            title="Nessuna associazione registrata"
            detail="Le associazioni nascono dall'anteprima dell'importazione, quando un valore dell'Excel non corrisponde a nessuna voce censita."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="py-2">Tipo</th>
                  <th className="py-2">Valore nell'Excel</th>
                  <th className="py-2">Destinazione</th>
                  <th className="py-2">Contesto</th>
                  <th className="py-2">Confermata da</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody>
                {righe.map((a) => (
                  <tr key={a.id} className="border-t border-border">
                    <td className="py-2">{a.tipo_etichetta}</td>
                    <td className="py-2 font-mono text-xs">{a.valore}</td>
                    <td className="py-2">{a.destinazione}</td>
                    <td className="py-2 text-muted-foreground">
                      {a.semestre || (a.anno ? String(a.anno) : "—")}
                    </td>
                    <td className="py-2">{a.confermata_da ?? "—"}</td>
                    <td className="py-2 text-right">
                      <Button
                        type="button"
                        variant="danger"
                        disabled={elimina.isPending}
                        onClick={() => elimina.mutate(a.id)}
                        aria-label={`Elimina associazione ${a.valore}`}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
