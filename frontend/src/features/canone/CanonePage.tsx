import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { DaysValue } from "@/components/DaysValue";
import { ErrorState, LoadingState } from "@/components/UiState";
import { api } from "@/lib/api";

interface CanoneIndex {
  id: string;
  semestre: string;
  progetto_codice: string;
  progetto_titolo: string;
}
interface CanoneStatus {
  semestre: string;
  monte: string;
  consuntivato: string;
  target_alla_data: string;
  delta: string;
  forecast: string;
  percentuale_forecast: string;
  proiezione: string;
  giornate_non_usate_previste: string;
  formula_target: string;
  per_ufficio: Record<
    string,
    {
      consuntivato: string;
      stima_trimestre: string;
      forecast_residuo: string;
      sottoattivita: {
        codice: string;
        titolo: string;
        consuntivato: string;
        stima_trimestre: string;
        forecast_residuo: string;
      }[];
    }
  >;
  burndown: { data: string; consumato: string; target: string }[];
}

export function CanonePage() {
  const index = useQuery({
    queryKey: ["canoni"],
    queryFn: () => api.get<{ results: CanoneIndex[] }>("/canoni"),
  });
  const [selected, setSelected] = useState<string>("");
  const canoneId = selected || index.data?.results[0]?.id || "";
  const status = useQuery({
    queryKey: ["canone", canoneId, "status"],
    queryFn: () => api.get<CanoneStatus>(`/canoni/${canoneId}/status`),
    enabled: canoneId !== "",
  });
  if (index.isLoading || (canoneId && status.isLoading)) return <LoadingState />;
  if (index.isError || status.isError) return <ErrorState title="Impossibile caricare i canoni" />;
  if (!status.data) return <ErrorState title="Nessun canone disponibile" />;
  const data = status.data;
  return (
    <section className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Canone</h1>
          <p className="text-sm text-muted-foreground">
            Target, delta e forecast calcolati dal dominio.
          </p>
        </div>
        <label className="text-sm">
          Semestre
          <select
            className="ml-2 h-9 rounded-md border border-input bg-background px-3"
            value={canoneId}
            onChange={(event) => setSelected(event.target.value)}
          >
            {index.data?.results.map((item) => (
              <option key={item.id} value={item.id}>
                {item.semestre} · {item.progetto_codice}
              </option>
            ))}
          </select>
        </label>
      </header>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {[
          ["Monte", data.monte],
          ["Consuntivato", data.consuntivato],
          ["Target alla data", data.target_alla_data],
          ["Delta", data.delta],
          ["Forecast", data.forecast],
        ].map(([label, value]) => (
          <article
            key={label}
            className="rounded-lg border border-border bg-card p-4"
            title={label === "Target alla data" ? data.formula_target : undefined}
          >
            <p className="text-xs uppercase text-muted-foreground">{label}</p>
            <DaysValue
              value={value}
              className="mt-2 block font-mono text-xl font-semibold tabular-nums"
            />
          </article>
        ))}
      </div>
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="font-medium">Andamento</h2>
        <div
          className="mt-4 flex h-48 items-end gap-1 overflow-x-auto border-b border-l border-border p-2"
          aria-label="Burn-down canone"
        >
          {data.burndown.map((point) => (
            <div
              key={point.data}
              className="group flex min-w-3 flex-1 items-end"
              title={`${point.data}: consumato ${point.consumato} gg, target ${point.target} gg`}
            >
              <div
                className="w-full rounded-t bg-accent/70"
                style={{
                  height: `${Math.max(3, Math.min(100, Number.parseFloat(point.consumato)))}%`,
                }}
              />
            </div>
          ))}
        </div>
      </section>
      <section className="overflow-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="bg-muted text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="p-3">Ufficio</th>
              <th className="p-3">Consuntivato</th>
              <th className="p-3">Stima trimestre</th>
              <th className="p-3">Forecast residuo</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.per_ufficio).map(([office, row]) => (
              <tr key={office} className="border-t border-border">
                <td className="p-3 font-medium">{office}</td>
                <td className="p-3">
                  <DaysValue value={row.consuntivato} />
                </td>
                <td className="p-3">
                  <DaysValue value={row.stima_trimestre} />
                </td>
                <td className="p-3">
                  <DaysValue value={row.forecast_residuo} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </section>
  );
}
