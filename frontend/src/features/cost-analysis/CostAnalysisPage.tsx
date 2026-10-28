import { PageHeader } from "@/components/PageHeader";
import { Button, Input, Select } from "@/components/Controls";
import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AccessibleBarChart } from "@/components/AccessibleBarChart";
import { MetricLabel } from "@/components/InfoTooltip";
import { ResizableTableHeader } from "@/components/ResizableTableHeader";
import { ErrorState, LoadingState } from "@/components/UiState";
import { api } from "@/lib/api";
import { formatDays } from "@/lib/format";

interface Row {
  label: string;
  days: string | null;
  cost: string;
}
interface SourceRow {
  source: string;
  days: string | null;
  cost: string;
}
interface TrendRow {
  month: string;
  days: string | null;
  cost: string;
}
interface CostAnalysis {
  policy: string;
  kpi: {
    total_days: string;
    total_cost: string;
    daily_person_cost: string;
    canone_total_cost?: string;
    canone_count?: number;
    canone_fixed_cost?: string;
  };
  by_project: Row[];
  by_supplier: Row[];
  by_source: SourceRow[];
  monthly_trend: TrendRow[];
}

const money = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });

function AggregationTable({ title, rows }: { title: string; rows: Row[] }) {
  const { t } = useTranslation();
  return (
    <section className="overflow-hidden rounded-lg border border-border bg-card">
      <h2 className="p-4 font-semibold">{title}</h2>
      <div className="overflow-x-auto">
        <table className="w-full table-fixed text-sm">
          <thead className="bg-muted/50">
            <tr>
              <ResizableTableHeader initialWidth={220}>
                {t("costAnalysis.label")}
              </ResizableTableHeader>
              <ResizableTableHeader initialWidth={100} align="right">
                {t("costAnalysis.days")}
              </ResizableTableHeader>
              <ResizableTableHeader initialWidth={120} align="right">
                {t("costAnalysis.cost")}
              </ResizableTableHeader>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={3} className="p-4 text-center text-muted-foreground">
                  Nessun dato per questa aggregazione.
                </td>
              </tr>
            )}
            {rows.map((row) => (
              <tr key={row.label} className="border-t border-border">
                <td className="truncate p-3" title={row.label}>
                  {row.label}
                </td>
                <td className="p-3 text-right tabular-nums">{formatDays(row.days)}</td>
                <td className="p-3 text-right tabular-nums">{money.format(Number(row.cost))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function CostAnalysisPage() {
  const { t } = useTranslation();
  const [draftFrom, setDraftFrom] = useState("");
  const [draftTo, setDraftTo] = useState("");
  const [draftIncludeCanone, setDraftIncludeCanone] = useState(false);
  const [filters, setFilters] = useState({ from: "", to: "", includeCanone: false });
  const [projectSearch, setProjectSearch] = useState("");
  const [projectLimit, setProjectLimit] = useState(10);
  const query = useQuery({
    queryKey: ["cost-analysis", filters],
    queryFn: () => {
      const params = new URLSearchParams();
      if (filters.from) params.set("from", filters.from);
      if (filters.to) params.set("to", filters.to);
      if (filters.includeCanone) params.set("include_canone", "true");
      return api.get<CostAnalysis>(`/cost-analysis${params.size ? `?${params}` : ""}`);
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setFilters({ from: draftFrom, to: draftTo, includeCanone: draftIncludeCanone });
  };
  if (query.isLoading) return <LoadingState />;
  if (query.isError || !query.data)
    return (
      <ErrorState
        title={t("costAnalysis.error")}
        detail={query.error instanceof Error ? query.error.message : undefined}
      />
    );
  const data = query.data;
  const empty = data.by_project.length === 0;
  const normalizedSearch = projectSearch.trim().toLocaleLowerCase();
  const sortedProjects = [...data.by_project].sort(
    (left, right) =>
      Number(right.cost) - Number(left.cost) || left.label.localeCompare(right.label),
  );
  const matchingProjects = sortedProjects.filter((row) =>
    row.label.toLocaleLowerCase().includes(normalizedSearch),
  );
  const chartProjects = matchingProjects.slice(0, projectLimit);
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Controllo · Analisi economica"
        title={t("costAnalysis.title")}
        description={<> {data.policy} </>}
      />
      <form
        onSubmit={submit}
        className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-card p-4"
      >
        <label className="text-sm">
          {t("costAnalysis.from")}
          <Input
            aria-label={t("costAnalysis.from")}
            type="date"
            value={draftFrom}
            onChange={(e) => setDraftFrom(e.target.value)}
            className="mt-1 block rounded-md border border-input bg-background px-3 py-2"
          />
        </label>
        <label className="text-sm">
          {t("costAnalysis.to")}
          <Input
            aria-label={t("costAnalysis.to")}
            type="date"
            value={draftTo}
            onChange={(e) => setDraftTo(e.target.value)}
            className="mt-1 block rounded-md border border-input bg-background px-3 py-2"
          />
        </label>
        <label className="flex items-center gap-2 py-2 text-sm">
          <input
            type="checkbox"
            checked={draftIncludeCanone}
            onChange={(event) => setDraftIncludeCanone(event.target.checked)}
            aria-describedby="canone-cost-policy"
            className="h-4 w-4 accent-primary"
          />
          Considera i costi del canone
        </label>
        <Button className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground">
          {t("costAnalysis.apply")}
        </Button>
      </form>
      <p id="canone-cost-policy" className="text-sm text-muted-foreground">
        Le giornate del canone sono escluse dai costi a giornata. Applica i filtri per includere il
        forfait completo dei canoni la cui attivazione rientra nel periodo selezionato. In assenza
        di una data di inizio viene usato l'inizio del periodo contrattuale.
      </p>
      {filters.includeCanone && (
        <div role="status" className="rounded-lg border border-border bg-card p-4 text-sm">
          <span className="font-semibold">
            Canone: {money.format(Number(data.kpi.canone_total_cost ?? 0))}
          </span>
          <span className="text-muted-foreground">
            {" "}
            - {data.kpi.canone_count ?? 0} contratti attivati nel periodo, forfait per contratto{" "}
            {money.format(Number(data.kpi.canone_fixed_cost ?? 0))}.
          </span>
          {Number(data.kpi.canone_fixed_cost ?? 0) === 0 && (
            <p className="mt-1 text-amber-700 dark:text-amber-300">
              Configura il costo forfettario del canone in Amministrazione / Configurazione.
            </p>
          )}
        </div>
      )}
      {Number(data.kpi.daily_person_cost) === 0 && (
        <div
          role="alert"
          className="flex gap-2 rounded-md border border-amber-400 bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100"
        >
          <AlertTriangle className="h-5 w-5" />
          {t("costAnalysis.zeroCost")}
        </div>
      )}
      <section className="grid gap-3 sm:grid-cols-3">
        {(
          [
            [
              "Giornate a tariffa giornaliera",
              formatDays(data.kpi.total_days),
              "Giornate di progetti e wallet nel periodo selezionato. I consuntivi del canone sono esclusi.",
            ],
            [
              t("costAnalysis.totalCost"),
              money.format(Number(data.kpi.total_cost)),
              "Costo delle giornate di progetti e wallet, più il forfait completo dei canoni se il flag è attivo.",
            ],
            [
              "Tariffa giornaliera progetti e wallet",
              money.format(Number(data.kpi.daily_person_cost)),
              "Tariffa applicata alle giornate di progetti e wallet. Il canone ha un costo forfettario separato.",
            ],
          ] satisfies Array<[string, string, string]>
        ).map(([label, value, description]) => (
          <article key={label} className="rounded-lg border border-border bg-card p-4">
            <MetricLabel label={label} description={description} />
            <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
          </article>
        ))}
      </section>
      {empty ? (
        <p className="rounded-lg border border-border bg-card p-8 text-center text-muted-foreground">
          Nessun costo o giornata a tariffa giornaliera nel periodo selezionato.
        </p>
      ) : (
        <>
          <section
            className="rounded-xl border border-border bg-card p-4 shadow-subtle"
            aria-labelledby="project-cost-chart-title"
            aria-describedby="project-cost-chart-description"
          >
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 id="project-cost-chart-title" className="font-semibold">
                  {filters.includeCanone
                    ? "Costi per progetto e canone"
                    : t("costAnalysis.projectChart")}
                </h2>
                <p id="project-cost-chart-description" className="text-sm text-muted-foreground">
                  {t("costAnalysis.projectChartDescription")}
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <Input
                  type="search"
                  aria-label={t("costAnalysis.projectSearch")}
                  value={projectSearch}
                  onChange={(event) => setProjectSearch(event.target.value)}
                  placeholder={t("costAnalysis.projectSearch")}
                  className="rounded-md border border-input bg-background px-3 py-2 text-sm"
                />
                <Select
                  aria-label={t("costAnalysis.projectLimit")}
                  value={projectLimit}
                  onChange={(event) => setProjectLimit(Number(event.target.value))}
                  className="rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  {[5, 10, 20].map((limit) => (
                    <option key={limit} value={limit}>
                      Top {limit}
                    </option>
                  ))}
                </Select>
              </div>
            </div>
            {chartProjects.length ? (
              <>
                <div
                  className="mt-4"
                  style={{ height: Math.max(180, chartProjects.length * 38 + 40) }}
                  aria-hidden="true"
                >
                  <AccessibleBarChart
                    data={chartProjects.map((row) => ({ ...row, cost: Number(row.cost) }))}
                    xKey="label"
                    unit="euro"
                    hideXAxis
                    horizontal
                    series={[{ key: "cost", label: t("costAnalysis.cost"), color: "#6366f1" }]}
                  />
                </div>
                <table
                  className="mt-4 w-full text-sm"
                  aria-label={t("costAnalysis.projectChartSummary")}
                >
                  <thead className="sr-only">
                    <tr>
                      <th>{t("costAnalysis.label")}</th>
                      <th>{t("costAnalysis.cost")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {chartProjects.map((row) => (
                      <tr key={row.label}>
                        <td className="py-2 pr-4">{row.label}</td>
                        <td className="py-2 text-right font-medium tabular-nums">
                          {money.format(Number(row.cost))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            ) : (
              <p className="mt-4 rounded-lg bg-muted/40 p-8 text-center text-muted-foreground">
                {t("costAnalysis.noMatchingProjects")}
              </p>
            )}
          </section>
          <div className="grid gap-5 xl:grid-cols-2">
            <AggregationTable
              title={
                filters.includeCanone
                  ? "Dettaglio per progetto e canone"
                  : t("costAnalysis.byProject")
              }
              rows={data.by_project}
            />
            <AggregationTable title={t("costAnalysis.bySupplier")} rows={data.by_supplier} />
          </div>
          <AggregationTable
            title={t("costAnalysis.bySource")}
            rows={data.by_source.map((row) => ({
              ...row,
              label: row.source === "CANONE" ? "Canone" : row.source,
            }))}
          />
          <AggregationTable
            title={t("costAnalysis.monthlyTrend")}
            rows={data.monthly_trend.map((row) => ({ ...row, label: row.month }))}
          />
        </>
      )}
    </div>
  );
}
