import { useQuery } from "@tanstack/react-query";

import { DaysValue } from "@/components/DaysValue";
import { KpiCard } from "@/components/KpiCard";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorState, LoadingState } from "@/components/UiState";
import { api } from "@/lib/api";
import { formatPercent } from "@/lib/format";

interface Row {
  codice_progetto: string;
  progetto_id: string;
  interno: string;
  ppm: string | null;
  delta: string | null;
  esito: string;
  snapshot_estratto_il: string | null;
  azione_suggerita: string;
}
interface Response {
  riepilogo: {
    stato: "ALLINEATO" | "NON_ALLINEATO" | "PARZIALE" | "NON_VERIFICABILE";
    stato_dati: "DISPONIBILI" | "SNAPSHOT_ASSENTE" | "NESSUNA_RIGA_CONFRONTABILE";
    righe: number;
    righe_confrontabili: number;
    ok: number;
    ko: number;
    assenti_in_ppm: number;
    delta_totale: string | null;
    percentuale_allineati: string | null;
    snapshot_estratto_il: string | null;
  };
  tolleranza: string;
  results?: Row[];
  risultati?: Row[];
}

export function ReconciliationPage() {
  const query = useQuery({
    queryKey: ["reconciliation", "latest", "page"],
    queryFn: () => api.get<Response>("/reconciliation/latest"),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError || !query.data)
    return <ErrorState title="Impossibile caricare la riconciliazione" />;
  const { riepilogo } = query.data;
  const rows = query.data.results ?? query.data.risultati ?? [];
  const dataMessage =
    riepilogo.stato_dati === "SNAPSHOT_ASSENTE"
      ? "Snapshot PPM assente: la riconciliazione non può essere eseguita."
      : riepilogo.stato_dati === "NESSUNA_RIGA_CONFRONTABILE"
        ? "Lo snapshot è presente, ma non contiene righe confrontabili."
        : null;
  return (
    <section className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold">Riconciliazione PPM</h1>
        <p className="text-sm text-muted-foreground">
          Confronto fra ledger interno e ultimo snapshot del fornitore · tolleranza{" "}
          <DaysValue value={query.data.tolleranza} />
        </p>
        <div className="mt-3 flex items-center gap-3">
          <StatusBadge status={riepilogo.stato} />
          {dataMessage && <span className="text-sm text-muted-foreground">{dataMessage}</span>}
        </div>
      </header>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Confronti eseguiti"
          value={riepilogo.righe_confrontabili}
          hint={`${riepilogo.righe} righe rilevanti`}
        />
        <KpiCard
          label="Allineate"
          value={
            riepilogo.percentuale_allineati === null
              ? "Non disponibile"
              : `${riepilogo.ok} · ${formatPercent(riepilogo.percentuale_allineati)}`
          }
          tone={riepilogo.stato === "ALLINEATO" ? "ok" : "neutral"}
        />
        <KpiCard
          label="Non allineate"
          value={riepilogo.righe_confrontabili === 0 ? "Non disponibile" : riepilogo.ko}
          tone={riepilogo.ko > 0 ? "danger" : "neutral"}
        />
        <KpiCard
          label="Assenti in PPM"
          value={riepilogo.assenti_in_ppm}
          tone={riepilogo.assenti_in_ppm > 0 ? "warn" : "neutral"}
        />
      </div>
      <div className="overflow-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="bg-muted text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="p-3">Progetto</th>
              <th className="p-3">Interno</th>
              <th className="p-3">PPM</th>
              <th className="p-3">Delta</th>
              <th className="p-3">Esito</th>
              <th className="p-3">Azione</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.progetto_id} className="border-t border-border">
                <td className="p-3 font-mono">{row.codice_progetto.split("-", 1)[0]}</td>
                <td className="p-3">
                  <DaysValue value={row.interno} />
                </td>
                <td className="p-3">
                  <DaysValue value={row.ppm} />
                </td>
                <td className="p-3">
                  <DaysValue value={row.delta} />
                </td>
                <td className="p-3">
                  <StatusBadge status={row.esito} />
                </td>
                <td className="max-w-sm p-3 text-xs text-muted-foreground">
                  {row.azione_suggerita}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td className="p-6 text-center text-muted-foreground" colSpan={6}>
                  {dataMessage ?? "Nessun dato disponibile."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
