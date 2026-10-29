import { KpiCard } from "@/components/KpiCard";
import { useQuery } from "@tanstack/react-query";
import * as Tooltip from "@radix-ui/react-tooltip";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DonutChart, type ChartDatum } from "./DashboardCharts";
import { InfoTooltip } from "@/components/InfoTooltip";
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
  distribuzione_referenti: {
    referente_id: string | null;
    referente: string;
    progetti: number;
    attivita_wallet: number;
    giornate_progetti: string;
    giornate_wallet: string;
    monte_giornate: string;
  }[];
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
      classificazione: "MESE_CORRENTE" | "ARRETRATA";
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
      label: t(`status.${item.stato}`, {
        defaultValue: item.stato.replaceAll("_", " ").toLocaleLowerCase("it"),
      }),
      value: item.conteggio,
      color: CHART_COLORS[index % CHART_COLORS.length]!,
    })) ?? [];
  const dashboardWallet = dashboard.data?.wallet;
  const chartValue = (value: unknown) =>
    typeof value === "string" && value.trim() ? Number(value) : NaN;
  const walletChart: ChartDatum[] = dashboardWallet
    ? [
        {
          key: "consumato",
          label: t("wallet.consumed"),
          value: chartValue(dashboardWallet.consumato),
          color: CHART_COLORS[3],
        },
        {
          key: "disponibile",
          label: t("wallet.available"),
          value: chartValue(dashboardWallet.disponibile),
          color: CHART_COLORS[1],
        },
      ]
    : [];

  return (
    <section className="space-y-6">
      <header className="relative overflow-hidden rounded-2xl border border-border bg-card px-6 py-7 md:px-8">
        <div aria-hidden="true" className="absolute right-0 top-0 h-full w-1/3 bg-accent/5" />
        <p className="relative text-xs font-semibold uppercase tracking-[0.2em] text-accent">
          Supplier Ledger · Overview
        </p>
        <div className="relative mt-3 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t("dashboard.title")}</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Controllo economico e operativo del portafoglio
            </p>
          </div>
          <span className="rounded-full border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground">
            Anno {year}
          </span>
        </div>
      </header>

      {(wallet.isError || reconciliation.isError) && (
        <div
          role="alert"
          className="rounded-xl border border-danger/30 bg-danger-subtle p-4 text-sm text-danger"
        >
          Alcuni indicatori non sono disponibili perché il caricamento dei dati è fallito.
        </div>
      )}

      <section aria-label="Situazione economica" className="space-y-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Situazione economica</h2>
          <p className="text-sm text-muted-foreground">
            Disponibilità, residui e confronto con il fornitore
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
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
                featured
                label={t("wallet.available")}
                value={wallet.isError ? "Errore caricamento" : formatDays(wallet.data?.disponibile)}
                hint={`${t("wallet.allocated")} ${formatDays(wallet.data?.allocato)} · ${t(
                  "wallet.consumed",
                )} ${formatDays(wallet.data?.consumato)}`}
                tooltip={`Disponibile = allocato (${formatDays(wallet.data?.allocato)}) − consumato (${formatDays(wallet.data?.consumato)}) = ${formatDays(wallet.data?.disponibile)}`}
                tone={wallet.isError ? "neutral" : "ok"}
              />
              <KpiCard
                label={t("wallet.ongoingBudget")}
                value={
                  wallet.isError
                    ? "Errore caricamento"
                    : formatDays(wallet.data?.budget_residuo_progetti_in_corso)
                }
                hint={`Separato dal wallet · ${t("wallet.ongoingOverrun")}: ${formatDays(wallet.data?.sforamenti_progetti_in_corso)}`}
                tooltip={`Budget residuo progetti in corso al netto dei rilasci al wallet. Sforamenti: ${formatDays(wallet.data?.sforamenti_progetti_in_corso)}`}
                tone="neutral"
              />
              <KpiCard
                label={t("wallet.potential")}
                value={
                  wallet.isError
                    ? "Errore caricamento"
                    : formatDays(wallet.data?.residui_potenziali_da_verificare)
                }
                hint="Esclusi dal disponibile ufficiale"
                tooltip="Residui da verificare o chiusi senza data; non spendibili finché non chiariti"
                action={
                  <Link
                    to="/revisione"
                    className="inline-flex items-center text-primary underline underline-offset-4 hover:opacity-80"
                  >
                    {t("wallet.reviewQueueLink")} &rarr;
                  </Link>
                }
                tone={wallet.isError ? "neutral" : "warn"}
              />
              <KpiCard
                label={t("dashboard.reconciliationDelta")}
                value={
                  reconciliation.isError
                    ? "Errore caricamento"
                    : reconciliation.data?.riepilogo.delta_totale === null
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
      </section>

      <section aria-label="Distribuzione e composizione" className="space-y-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Portafoglio e wallet</h2>
          <p className="text-sm text-muted-foreground">Composizione dei dati disponibili</p>
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          {dashboard.isLoading ? (
            <>
              <SkeletonCard />
              <SkeletonCard />
            </>
          ) : dashboard.isError ? (
            <div className="rounded-lg border border-danger/30 bg-danger-subtle p-4 text-sm text-danger xl:col-span-2">
              {t("dashboard.dataError")}
            </div>
          ) : (
            <>
              <DonutChart title={t("dashboard.projectsByStatus")} data={projectChart} premium />
              {walletChart.some((item) => !Number.isFinite(item.value) || item.value < 0) ? (
                <div className="rounded-xl border border-border bg-card p-5 text-sm text-muted-foreground">
                  <h2 className="font-semibold text-foreground">
                    {t("dashboard.walletComposition")}
                  </h2>
                  <p className="mt-3">
                    La composizione non è rappresentabile come grafico: uno o più valori sono
                    negativi o non disponibili.
                  </p>
                </div>
              ) : (
                <DonutChart
                  title={t("dashboard.walletComposition")}
                  data={walletChart}
                  unit="days"
                />
              )}
            </>
          )}
        </div>
      </section>

      <section
        className="relative overflow-hidden rounded-2xl border border-border bg-card p-5 shadow-subtle sm:p-6"
        aria-labelledby="referent-distribution-title"
      >
        <h2 id="referent-distribution-title" className="text-lg font-semibold tracking-tight">
          Distribuzione per referente BMED
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Numero di progetti e attività wallet per referente, considerando tutti gli stati e tutti
          gli anni. Le attività tecniche sono escluse.
        </p>
        {dashboard.isLoading ? (
          <div className="skeleton mt-4 h-32 w-full" />
        ) : dashboard.isError ? (
          <p className="mt-4 text-sm text-danger">{t("dashboard.dataError")}</p>
        ) : !dashboard.data?.distribuzione_referenti?.length ? (
          <p className="mt-4 rounded-md bg-muted/40 p-6 text-center text-sm text-muted-foreground">
            Nessun progetto o attività wallet disponibile.
          </p>
        ) : (
          <div className="mt-6 space-y-5">
            <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
              <span className="flex items-center gap-2">
                <span
                  className="size-2.5 rounded-full bg-gradient-to-r from-indigo-600 to-blue-400"
                  aria-hidden="true"
                />
                Progetti
              </span>
              <span className="flex items-center gap-2">
                <span
                  className="size-2.5 rounded-full bg-gradient-to-r from-cyan-600 to-sky-400"
                  aria-hidden="true"
                />
                Attività wallet
              </span>
            </div>
            <ul className="divide-y divide-border/70">
              {dashboard.data.distribuzione_referenti.map((row) => {
                const max = Math.max(
                  ...dashboard.data.distribuzione_referenti.flatMap((item) => [
                    item.progetti,
                    item.attivita_wallet,
                  ]),
                  1,
                );
                return (
                  <li
                    key={row.referente_id ?? "unassigned"}
                    className="grid gap-3 py-4 first:pt-0 last:pb-0 sm:grid-cols-[minmax(10rem,15rem)_minmax(0,1fr)] sm:items-center"
                  >
                    <span className="break-words text-sm font-semibold">{row.referente}</span>
                    <div className="space-y-2">
                      {[
                        [
                          "Progetti",
                          row.progetti,
                          "bg-gradient-to-r from-indigo-600 via-blue-500 to-sky-400",
                        ],
                        [
                          "Attività wallet",
                          row.attivita_wallet,
                          "bg-gradient-to-r from-cyan-600 via-cyan-500 to-teal-300",
                        ],
                      ].map(([label, count, color]) => (
                        <Tooltip.Provider key={label} delayDuration={150}>
                          <Tooltip.Root>
                            <Tooltip.Trigger asChild>
                              <button
                                type="button"
                                className="group flex min-h-6 w-full items-center gap-3 rounded-md text-left"
                                aria-label={`${row.referente}: ${label}, ${count}. Mostra dettaglio`}
                              >
                                <span className="sr-only">{label}: </span>
                                <div
                                  className="h-3 flex-1 overflow-hidden rounded-full bg-muted shadow-inner"
                                  aria-hidden="true"
                                >
                                  <div
                                    className={`h-full rounded-full shadow-sm transition-[filter] duration-200 group-hover:brightness-110 ${color}`}
                                    style={{ width: `${(Number(count) / max) * 100}%` }}
                                  />
                                </div>
                                <span className="w-9 text-right text-sm font-semibold tabular-nums text-foreground">
                                  {count}
                                </span>
                              </button>
                            </Tooltip.Trigger>
                            <Tooltip.Portal>
                              <Tooltip.Content
                                sideOffset={8}
                                collisionPadding={12}
                                className="z-[100] w-64 rounded-xl border border-sky-300/20 bg-[#101d38] p-4 text-sm text-white shadow-[0_16px_40px_rgba(0,0,0,0.3)]"
                              >
                                <p className="mb-3 border-b border-white/10 pb-3 text-sm font-semibold tracking-tight">
                                  {row.referente}
                                </p>
                                <dl className="space-y-2">
                                  <div className="flex justify-between gap-3">
                                    <dt>Progetti</dt>
                                    <dd>{row.progetti}</dd>
                                  </div>
                                  <div className="flex justify-between gap-3">
                                    <dt>Wallet</dt>
                                    <dd>{row.attivita_wallet}</dd>
                                  </div>
                                  <div className="flex justify-between gap-3 border-t border-slate-700 pt-2 font-semibold">
                                    <dt>Monte GG gestite</dt>
                                    <dd>{formatDays(row.monte_giornate)}</dd>
                                  </div>
                                </dl>
                                <Tooltip.Arrow className="fill-[#101d38]" />
                              </Tooltip.Content>
                            </Tooltip.Portal>
                          </Tooltip.Root>
                        </Tooltip.Provider>
                      ))}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-border bg-card p-5 shadow-subtle">
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
                  <th className="px-2 py-2">{t("dashboard.billingTiming")}</th>
                  <th className="px-2 py-2">{t("project.code")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {dashboard.data.prossime_fatturazioni.results.map((item) => (
                  <tr key={item.id}>
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
                      {t(
                        item.classificazione === "ARRETRATA"
                          ? "dashboard.overdueBilling"
                          : "dashboard.currentBilling",
                      )}
                    </td>
                    <td className="px-2 py-3 font-medium">
                      <Link
                        className="text-accent hover:underline dark:text-indigo-300"
                        to={`/progetti/${item.progetto_id}`}
                      >
                        {item.progetto_codice}
                      </Link>
                    </td>
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
