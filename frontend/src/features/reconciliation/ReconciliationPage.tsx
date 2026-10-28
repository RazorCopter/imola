import { Input, Select } from "@/components/Controls";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { DaysValue } from "@/components/DaysValue";
import { KpiCard } from "@/components/KpiCard";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorState, LoadingState } from "@/components/UiState";
import { getReconciliationOutcomePresentation } from "@/features/reconciliation/reconciliationOutcome";
import { api } from "@/lib/api";
import { formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Row {
  codice_progetto: string;
  nome_progetto: string | null;
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

function OutcomeBadge({ outcome }: { outcome: string }) {
  const presentation = getReconciliationOutcomePresentation(outcome);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold",
        presentation.tone === "ok" && "border-ok/40 bg-ok-subtle text-ok",
        presentation.tone === "warn" && "border-warn/40 bg-warn-subtle text-warn",
        presentation.tone === "danger" && "border-danger/40 bg-danger-subtle text-danger",
        presentation.tone === "neutral" && "border-border bg-muted text-foreground",
      )}
      data-outcome={outcome || "UNKNOWN"}
      data-tone={presentation.tone}
      title={presentation.known ? `Esito: ${presentation.label}` : presentation.label}
    >
      {presentation.label}
    </span>
  );
}

export function ReconciliationPage() {
  const [search, setSearch] = useState("");
  const [outcome, setOutcome] = useState("");
  const query = useQuery({
    queryKey: ["reconciliation", "latest", "page"],
    queryFn: () => api.get<Response>("/reconciliation/latest"),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError || !query.data)
    return <ErrorState title="Impossibile caricare la riconciliazione" />;
  const { riepilogo } = query.data;
  const rows = (query.data.results ?? query.data.risultati ?? []).filter(
    (row) =>
      (!outcome || row.esito === outcome) &&
      `${row.codice_progetto} ${row.nome_progetto ?? ""}`
        .toLocaleLowerCase("it")
        .includes(search.trim().toLocaleLowerCase("it")),
  );
  const dataMessage =
    riepilogo.stato_dati === "SNAPSHOT_ASSENTE"
      ? "Snapshot PPM assente: la riconciliazione non può essere eseguita."
      : riepilogo.stato_dati === "NESSUNA_RIGA_CONFRONTABILE"
        ? "Lo snapshot è presente, ma non contiene righe confrontabili."
        : null;
  return (
    <section className="space-y-5">
      <header>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-accent">
          Controllo · Confronto fornitore
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Riconciliazione PPM</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Confronto fra ledger interno e ultimo snapshot del fornitore · tolleranza{" "}
          <DaysValue value={query.data.tolleranza} />
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card p-4">
          <StatusBadge status={riepilogo.stato} />
          {dataMessage && <span className="text-sm text-muted-foreground">{dataMessage}</span>}
        </div>
      </header>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Confronti eseguiti"
          value={riepilogo.righe_confrontabili}
          hint={`${riepilogo.righe} righe rilevanti`}
          tooltip="Numero di progetti per cui esistono sia un totale interno sia un valore PPM confrontabile."
        />
        <KpiCard
          label="Allineate"
          value={
            riepilogo.percentuale_allineati === null
              ? "Non disponibile"
              : `${riepilogo.ok} · ${formatPercent(riepilogo.percentuale_allineati)}`
          }
          tone={riepilogo.stato === "ALLINEATO" ? "ok" : "neutral"}
          tooltip="Progetti il cui scostamento tra consuntivo interno e PPM rientra nella tolleranza configurata."
        />
        <KpiCard
          label="Non allineate"
          value={riepilogo.righe_confrontabili === 0 ? "Non disponibile" : riepilogo.ko}
          tone={riepilogo.ko > 0 ? "danger" : "neutral"}
          tooltip="Progetti con una differenza tra consuntivo interno e PPM superiore alla tolleranza configurata."
        />
        <KpiCard
          label="Assenti in PPM"
          value={
            riepilogo.stato_dati === "SNAPSHOT_ASSENTE"
              ? "Non disponibile"
              : riepilogo.assenti_in_ppm
          }
          tone={riepilogo.assenti_in_ppm > 0 ? "warn" : "neutral"}
          tooltip="Progetti con consuntivi interni che non trovano una riga corrispondente nell’ultimo snapshot PPM."
        />
      </div>
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card p-3">
        <Input
          type="search"
          aria-label="Cerca progetto nella riconciliazione"
          placeholder="Cerca codice o progetto"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="h-9 min-w-48 flex-1 rounded-md border border-input bg-background px-3 text-sm"
        />
        <Select
          aria-label="Filtra esito riconciliazione"
          value={outcome}
          onChange={(event) => setOutcome(event.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
        >
          <option value="">Tutti gli esiti</option>
          <option value="OK">Allineati</option>
          <option value="KO">Discrepanze</option>
          <option value="ASSENTE_IN_PPM">Assenti in PPM</option>
        </Select>
        <span className="text-sm text-muted-foreground">{rows.length} risultati</span>
      </div>
      <div className="overflow-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="bg-muted text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="p-3">Progetto</th>
              <th className="p-3 text-right">Interno</th>
              <th className="p-3 text-right">PPM</th>
              <th className="p-3 text-right">Delta</th>
              <th className="p-3 text-center">Esito</th>
              <th className="p-3">Azione</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.progetto_id} className="border-t border-border">
                <td className="max-w-xs p-3">
                  <div className="font-medium" title={row.nome_progetto ?? undefined}>
                    {row.nome_progetto ?? "Progetto non associato"}
                  </div>
                  <Link
                    to={`/progetti/${row.progetto_id}`}
                    className="break-all text-xs text-accent underline-offset-4 hover:underline dark:text-indigo-300"
                  >
                    {row.codice_progetto}
                  </Link>
                </td>
                <td className="p-3 text-right">
                  <DaysValue value={row.interno} />
                </td>
                <td className="p-3 text-right">
                  <DaysValue value={row.ppm} />
                </td>
                <td className="p-3 text-right">
                  <DaysValue value={row.delta} />
                </td>
                <td className="p-3 text-center">
                  <OutcomeBadge outcome={row.esito} />
                </td>
                <td className="max-w-sm p-3 text-xs text-muted-foreground">
                  {row.azione_suggerita}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td className="p-6 text-center text-muted-foreground" colSpan={6}>
                  {dataMessage ??
                    (search || outcome
                      ? "Nessun progetto corrisponde ai filtri."
                      : "Nessun dato disponibile.")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
