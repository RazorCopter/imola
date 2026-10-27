import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DonutChart, type ChartDatum } from "./DashboardCharts";
import { InfoTooltip, MetricLabel } from "@/components/InfoTooltip";
import { api } from "@/lib/api";
import { formatDays, formatDelta, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

interface WalletBalance {
  anno: number;
  allocato: string;
  consumato: string;
  disponibile: string;
  disponibile_da_allocazioni: string;
  disponibile_da_allocazioni_aperte: string;
  capienza_wallet_potenziale: string;
  residui_validi_non_allocati: string;
  residui_in_scadenza: string;
  budget_residuo_progetti_in_corso: string;
  sforamenti_progetti_in_corso: string;
  residui_scaduti: string;
  residui_potenziali_da_verificare: string;
  dettaglio_residui?: Record<
    string,
    { giornate: string; progetti: { codice: string; giornate: string }[] }
  >;
}

interface ReconciliationSummary {
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
}

interface DashboardSummary {
  generato_il: string;
  progetti_per_stato: { stato: string; conteggio: number }[];
  wallet: { anno: number; allocato: string; consumato: string; disponibile: string };
  prossime_fatturazioni: {
    count: number;
    limit: number;
    results: {
      id: string;
      progetto_id: string;
      progetto_codice: string;
      data_pianificata: string;
      data_fatturazione: string;
      data_effettiva: string | null;
      classificazione: "MESE_CORRENTE";
      stato: string;
      numero_spostamenti: number;
      spostamenti: unknown[];
    }[];
  };
}

const CHART_COLORS: readonly [string, string, string, string] = [
  "#4f46e5",
  "#16a34a",
  "#d97706",
  "#dc2626",
];

function KpiCard({
  label,
  value,
  hint,
  tone = "neutral",
  tooltip,
  action,
}: {
  label: string;
  value: string;
  hint?: ReactNode;
  tone?: "neutral" | "ok" | "warn" | "danger";
  tooltip?: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-subtle">
      <MetricLabel label={label} description={tooltip ?? `Indicatore ${label}.`} />
      <p
        className={cn(
          "mt-2 font-mono text-2xl font-semibold tabular-nums",
          tone === "ok" && "text-ok",
          tone === "warn" && "text-warn",
          tone === "danger" && "text-danger",
        )}
      >
        {value}
      </p>
      {hint !== undefined && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
      {action !== undefined && <div className="mt-2 text-xs font-medium">{action}</div>}
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="skeleton h-3 w-24" />
      <div className="skeleton mt-3 h-7 w-32" />
    </div>
  );
}

export function DashboardPage() {
  const { t } = useTranslation();
  const year = new Date().getFullYear();

  const wallet = useQuery({
    queryKey: ["wallet", "balance", year],
    queryFn: () => api.get<WalletBalance>(`/wallet/${year}/balance`),
  });
  const reconciliation = useQuery({
    queryKey: ["reconciliation", "latest"],
    queryFn: () => api.get<ReconciliationSummary>("/reconciliation/latest"),
  });

  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<DashboardSummary>("/dashboard"),
  });

  const loading = wallet.isLoading || reconciliation.isLoading;
  const projectChart: ChartDatum[] =
    dashboard.data?.progetti_per_stato.map((item, index) => ({
      key: item.stato,
      label: t(`status.${item.stato}`),
      value: item.conteggio,
      color: CHART_COLORS[index % CHART_COLORS.length]!,
    })) ?? [];
  const dashboardWallet = dashboard.data?.wallet;
  const walletChart: ChartDatum[] = dashboardWallet
    ? [
        {
          key: "consumato",
          label: t("wallet.consumed"),
          value: Number(dashboardWallet.consumato),
          color: CHART_COLORS[3],
        },
        {
          key: "disponibile",
          label: t("wallet.available"),
          value: Number(dashboardWallet.disponibile),
          color: CHART_COLORS[1],
        },
      ]
    : [];

  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold tracking-tight">{t("dashboard.title")}</h1>
        <p className="text-sm text-muted-foreground">
          {t("wallet.available")} {year}
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {loading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : (
          <>
            <KpiCard
              label={t("wallet.available")}
              value={formatDays(wallet.data?.disponibile)}
              hint={`${t("wallet.allocated")} ${formatDays(wallet.data?.allocato)} · ${t(
                "wallet.consumed",
              )} ${formatDays(wallet.data?.consumato)}`}
              tooltip={`Disponibile = allocato (${formatDays(wallet.data?.allocato)}) − consumato (${formatDays(wallet.data?.consumato)}) = ${formatDays(wallet.data?.disponibile)}`}
              tone="ok"
            />
            <KpiCard
              label={t("wallet.ongoingBudget")}
              value={formatDays(wallet.data?.budget_residuo_progetti_in_corso)}
              hint={`Separato dal wallet · ${t("wallet.ongoingOverrun")}: ${formatDays(wallet.data?.sforamenti_progetti_in_corso)}`}
              tooltip={`Budget residuo progetti in corso al netto dei rilasci al wallet. Sforamenti: ${formatDays(wallet.data?.sforamenti_progetti_in_corso)}`}
              tone="neutral"
            />
            <KpiCard
              label={t("wallet.potential")}
              value={formatDays(wallet.data?.residui_potenziali_da_verificare)}
              hint="Esclusi dal disponibile ufficiale"
              tooltip="12 progetti da verificare o chiusi senza data; non spendibili finché non chiariti"
              action={
                <Link
                  to="/revisione"
                  className="text-primary inline-flex items-center underline underline-offset-4 hover:opacity-80"
                >
                  {t("wallet.reviewQueueLink")} &rarr;
                </Link>
              }
              tone="warn"
            />
            <KpiCard
              label={t("dashboard.reconciliationDelta")}
              value={
                reconciliation.data?.riepilogo.delta_totale === null
                  ? "Non disponibile"
                  : formatDelta(reconciliation.data?.riepilogo.delta_totale)
              }
              hint={
                reconciliation.data?.riepilogo.stato === "NON_VERIFICABILE"
                  ? "Riconciliazione non verificabile / dati assenti"
                  : reconciliation.data?.riepilogo.snapshot_estratto_il
                    ? `${t("dashboard.lastSnapshot")}: ${new Date(
                        reconciliation.data.riepilogo.snapshot_estratto_il,
                      ).toLocaleDateString("it-IT")}`
                    : t("app.empty")
              }
              tooltip="Differenza consuntivi interni vs ultimo estratto PPM fornitore"
              tone={
                reconciliation.data?.riepilogo.stato === "ALLINEATO"
                  ? "ok"
                  : reconciliation.data?.riepilogo.stato === "NON_ALLINEATO"
                    ? "danger"
                    : reconciliation.data?.riepilogo.stato === "PARZIALE"
                      ? "warn"
                      : "neutral"
              }
            />
          </>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {dashboard.isLoading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : dashboard.isError ? (
          <div className="rounded-lg border border-danger/30 bg-danger-subtle p-4 text-sm text-danger lg:col-span-2">
            {t("dashboard.dataError")}
          </div>
        ) : (
          <>
            <DonutChart title={t("dashboard.projectsByStatus")} data={projectChart} />
            <DonutChart title={t("dashboard.walletComposition")} data={walletChart} unit="days" />
          </>
        )}
      </div>

      <section className="rounded-lg border border-border bg-card p-4 shadow-subtle">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-semibold">{t("dashboard.upcomingBillings")}</h2>
          {dashboard.data && (
            <span className="text-xs text-muted-foreground">
              {t("dashboard.showingBillings", {
                shown: dashboard.data.prossime_fatturazioni.results.length,
                total: dashboard.data.prossime_fatturazioni.count,
              })}
            </span>
          )}
        </div>
        {dashboard.isLoading ? (
          <div className="skeleton mt-4 h-32 w-full" />
        ) : dashboard.isError ? (
          <p className="mt-4 text-sm text-danger">{t("dashboard.dataError")}</p>
        ) : dashboard.data?.prossime_fatturazioni.results.length ? (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[32rem] text-left text-sm">
              <thead className="border-b border-border text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-2 py-2">Data prevista</th>
                  <th className="px-2 py-2">{t("dashboard.billingDate")}</th>
                  <th className="px-2 py-2">{t("project.code")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {dashboard.data.prossime_fatturazioni.results.map((item) => (
                  <tr key={`${item.progetto_id}-${item.data_pianificata}`}>
                    <td className="whitespace-nowrap px-2 py-3 font-medium">
                      {new Intl.DateTimeFormat("it-IT", { timeZone: "UTC" }).format(
                        new Date(`${item.data_pianificata}T00:00:00Z`),
                      )}
                      {item.data_effettiva && (
                        <span className="block text-xs font-normal text-muted-foreground">
                          Effettiva:{" "}
                          {new Intl.DateTimeFormat("it-IT", { timeZone: "UTC" }).format(
                            new Date(`${item.data_effettiva}T00:00:00Z`),
                          )}
                        </span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-2 py-3 text-muted-foreground">
                      {new Intl.DateTimeFormat("it-IT", { timeZone: "UTC" }).format(
                        new Date(`${item.data_fatturazione}T00:00:00Z`),
                      )}
                    </td>
                    <td className="px-2 py-3 font-medium">{item.progetto_codice}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-4 rounded-md bg-muted/40 p-6 text-center text-sm text-muted-foreground">
            {t("dashboard.noUpcomingBillings")}
          </p>
        )}
      </section>

      {wallet.data !== undefined && (
        <div className="grid gap-4 lg:grid-cols-2">
          <section className="rounded-lg border border-border bg-card p-4">
            <h2 className="text-sm font-semibold">{t("dashboard.walletDetails")}</h2>
            <div className="mt-4 space-y-3">
              {(
                [
                  [
                    t("wallet.available"),
                    wallet.data.disponibile,
                    "bg-ok",
                    "Giornate ancora consumabili sulle attività wallet già allocate.",
                  ],
                  [
                    t("wallet.expiring"),
                    wallet.data.residui_in_scadenza,
                    "bg-warn",
                    "Residui wallet validi che raggiungeranno la scadenza entro la finestra configurata.",
                  ],
                  [
                    t("wallet.expired"),
                    wallet.data.residui_scaduti,
                    "bg-danger",
                    "Residui oltre la data limite e quindi non più utilizzabili per nuove allocazioni.",
                  ],
                  [
                    t("wallet.potential"),
                    wallet.data.residui_potenziali_da_verificare,
                    "bg-accent",
                    "Residui esclusi dal disponibile finché stato o data di chiusura del progetto non vengono confermati.",
                  ],
                ] as [string, string, string, string][]
              ).map(([label, value, color, description]) => (
                <div
                  key={label}
                  className="flex justify-between border-b border-border py-1 text-xs"
                >
                  <span className="flex items-center gap-2">
                    <span className={cn("border-l-4 pl-2", color.replace("bg-", "border-"))}>
                      {label}
                    </span>
                    <InfoTooltip label={label} description={description} />
                  </span>
                  <span className="font-mono tabular-nums">{formatDays(value)}</span>
                </div>
              ))}
            </div>
          </section>
          <section className="rounded-lg border border-border bg-card p-4">
            <h2 className="text-sm font-semibold">{t("dashboard.whatToDoNow")}</h2>
            <ul className="mt-3 space-y-2 text-sm">
              <li>
                <Link className="text-accent hover:underline" to="/revisione">
                  Verifica i residui potenziali
                </Link>
                <span className="ml-2 font-mono text-muted-foreground">
                  {formatDays(wallet.data.residui_potenziali_da_verificare)}
                </span>
              </li>
              <li>
                <Link className="text-accent hover:underline" to="/wallet">
                  Gestisci i residui in scadenza
                </Link>
                <span className="ml-2 font-mono text-muted-foreground">
                  {formatDays(wallet.data.residui_in_scadenza)}
                </span>
              </li>
              <li>
                <Link className="text-accent hover:underline" to="/progetti">
                  Controlla gli sforamenti attivi
                </Link>
                <span className="ml-2 font-mono text-muted-foreground">
                  {formatDays(wallet.data.sforamenti_progetti_in_corso)}
                </span>
              </li>
            </ul>
          </section>
        </div>
      )}

      {reconciliation.data !== undefined && (
        <div className="rounded-lg border border-border bg-card p-4 text-sm">
          <h2 className="font-medium">{t("nav.reconciliation")}</h2>
          <p className="mt-1 text-muted-foreground">
            {reconciliation.data.riepilogo.righe} righe ·{" "}
            <span className="text-ok">{reconciliation.data.riepilogo.ok} OK</span> ·{" "}
            <span className="text-danger">{reconciliation.data.riepilogo.ko} KO</span> ·{" "}
            {reconciliation.data.riepilogo.assenti_in_ppm} assenti in PPM ·{" "}
            {formatPercent(reconciliation.data.riepilogo.percentuale_allineati)} allineati
          </p>
        </div>
      )}
    </section>
  );
}
