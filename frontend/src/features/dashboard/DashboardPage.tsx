import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import * as Tooltip from "@radix-ui/react-tooltip";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowUpRight, Layers3, Wallet, Users, Coins, FileText, ArrowRight } from "lucide-react";
import { DonutChart, type ChartDatum } from "./DashboardCharts";
import { api } from "@/lib/api";
import { useSession } from "@/features/auth/session";
import { formatDays, formatDelta, formatPercent } from "@/lib/format";
import "./dashboard.css";

type Effort = { count: number; previsto: string; consumato: string };
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
  distribuzione_referenti_in_corso?: DashboardSummary["distribuzione_referenti"];
  operativita?: {
    progetti: Effort;
    wallet: Effort;
    organico: Effort & { allocato: string; non_allocato: string };
    progetti_superati: { id: string; titolo: string; sforamento: string }[];
  };
  economia?: { anno: number; total_cost: string; daily_person_cost: string };
  progetti_per_stato: { stato: string; conteggio: number }[];
  wallet: { anno: number; allocato: string; consumato: string; disponibile: string };
  prossime_fatturazioni: {
    count: number;
    limit: number;
    arretrate?: number;
    mese_corrente?: number;
    results: {
      id: string;
      progetto_id: string;
      progetto_codice: string;
      progetto_titolo?: string;
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

const euro = (value: string) =>
  new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(Number(value));
const percent = (used: string, total: string) =>
  Number(total) > 0 ? (Number(used) / Number(total)) * 100 : null;
function Consumption({ data }: { data?: Effort }) {
  if (!data) return <p className="dash-muted">Dati non disponibili</p>;
  const value = percent(data.consumato, data.previsto);
  return (
    <div className="dash-consumption">
      <div>
        <span>
          {formatDays(data.consumato)} / {formatDays(data.previsto)}
        </span>
        <strong>{value === null ? "N/D" : formatPercent(value)}</strong>
      </div>
      <div
        className="dash-track"
        role="img"
        aria-label={`Consumo ${value === null ? "non calcolabile" : formatPercent(value)}`}
      >
        <span
          className={value !== null && value > 100 ? "dash-over" : ""}
          style={{ width: `${Math.min(100, Math.max(0, value ?? 0))}%` }}
        />
      </div>
    </div>
  );
}
function Metric({
  title,
  value,
  tone,
  icon,
  children,
  to,
}: {
  title: string;
  value: ReactNode;
  tone: string;
  icon: ReactNode;
  children: ReactNode;
  to: string;
}) {
  return (
    <article className={`dash-metric dash-${tone}`}>
      <div className="dash-metric-heading">
        <span className="dash-icon">{icon}</span>
        <Link to={to} aria-label={`Apri ${title}`}>
          <ArrowUpRight size={18} />
        </Link>
      </div>
      <span className="dash-metric-title">{title}</span>
      <strong className="dash-metric-value">{value}</strong>
      {children}
    </article>
  );
}
function Loading() {
  return <div className="skeleton h-28 rounded-xl" aria-label="Caricamento indicatori" />;
}

export function DashboardPage() {
  const { t } = useTranslation();
  const { session } = useSession();
  const year = new Date().getFullYear();
  const [scope, setScope] = useState("active");
  const [measure, setMeasure] = useState("count");
  const [billingScope, setBillingScope] = useState("all");
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
  const data = dashboard.data;
  const ops = data?.operativita;
  const billings = data?.prossime_fatturazioni;
  const economy = data?.economia;
  const sources =
    scope === "active" ? data?.distribuzione_referenti_in_corso : data?.distribuzione_referenti;
  const score = (row: DashboardSummary["distribuzione_referenti"][number]) =>
    measure === "days" ? Number(row.monte_giornate) || 0 : row.progetti + row.attivita_wallet;
  const referents = [...(sources ?? [])].sort(
    (a, b) => score(b) - score(a) || a.referente.localeCompare(b.referente, "it"),
  );
  const max = Math.max(1, ...referents.map(score));
  const overdue = billings?.arretrate;
  const chartColors: Record<string, string> = {
    ATTIVO: "#3b82f6",
    CHIUSO: "#64748b",
    NON_AVVIATO: "#a78bfa",
    DA_VERIFICARE: "#d97706",
  };
  const projectChart: ChartDatum[] =
    data?.progetti_per_stato.map((x) => ({
      key: x.stato,
      label: t(`status.${x.stato}`, { defaultValue: x.stato }),
      value: x.conteggio,
      color: chartColors[x.stato] ?? "#64748b",
    })) ?? [];
  const recon = reconciliation.data?.riepilogo;
  const walletData = wallet.data;
  const visibleBillings =
    billings?.results.filter((x) => billingScope === "all" || x.classificazione === billingScope) ??
    [];
  return (
    <section className="dash-page">
      <header className="dash-header">
        <div>
          <p className="dash-eyebrow">ARCHITETTURE IT / CONTROLLO DI GESTIONE</p>
          <h1>{t("dashboard.title")}</h1>
          <p className="dash-muted">
            Progetti, fornitori e giornate. Le priorità a colpo d'occhio.
          </p>
        </div>
        <div className="dash-header-actions">
          <span className="dash-date">
            {data
              ? new Intl.DateTimeFormat("it-IT", { dateStyle: "long", timeZone: "UTC" }).format(
                  new Date(data.generato_il),
                )
              : `Anno ${year}`}
          </span>
          {(session?.is_admin || session?.roles.includes("admin")) && (
            <Link to="/report-gestionale" className="dash-report-button">
              <FileText size={16} />
              Report gestionale
            </Link>
          )}
        </div>
      </header>
      {(dashboard.isError || wallet.isError || reconciliation.isError) && (
        <div className="dash-error" role="alert">
          Alcuni indicatori non sono disponibili.{" "}
          <button
            onClick={() => {
              void dashboard.refetch();
              void wallet.refetch();
              void reconciliation.refetch();
            }}
          >
            Riprova
          </button>
        </div>
      )}
      <section className="dash-metrics" aria-label="Sintesi della gestione">
        {dashboard.isLoading ? (
          [0, 1, 2, 3].map((x) => <Loading key={x} />)
        ) : (
          <>
            <Metric
              title="Progetti attivi"
              tone="blue"
              icon={<Layers3 size={20} />}
              value={ops?.progetti.count ?? "—"}
              to="/progetti"
            >
              <Consumption data={ops?.progetti} />
              <p className="dash-caption">Consumo sul budget dei progetti attivi</p>
            </Metric>
            <Metric
              title="Attività wallet aperte"
              tone="cyan"
              icon={<Wallet size={20} />}
              value={ops?.wallet.count ?? "—"}
              to="/wallet"
            >
              <Consumption data={ops?.wallet} />
              <p className="dash-caption">Consumo delle allocazioni aperte, tutti gli anni</p>
            </Metric>
            <Metric
              title="Consumo organico"
              tone="violet"
              icon={<Users size={20} />}
              value={
                ops && percent(ops.organico.consumato, ops.organico.previsto) !== null
                  ? formatPercent(percent(ops.organico.consumato, ops.organico.previsto))
                  : "—"
              }
              to="/canone"
            >
              <Consumption data={ops?.organico} />
              <p className="dash-caption">
                {ops?.organico.count ?? "—"} attività in corso / canoni nel periodo corrente
              </p>
            </Metric>
            <Metric
              title={`Costo maturato ${economy?.anno ?? year}`}
              tone="navy"
              icon={<Coins size={20} />}
              value={
                economy && Number(economy.daily_person_cost) > 0
                  ? euro(economy.total_cost)
                  : "Non disponibile"
              }
              to="/analisi-costi"
            >
              <p className="dash-caption">
                Progetti e wallet, dal 1 gennaio.
                <br />
                Consuntivi × tariffa corrente, canoni esclusi.
              </p>
              <p className="dash-caption">
                {economy && Number(economy.daily_person_cost) > 0
                  ? `${euro(economy.daily_person_cost)} / gg. Valore maturato, non fatturato.`
                  : "Tariffa non configurata o dati assenti."}
              </p>
            </Metric>
          </>
        )}
      </section>
      <section aria-labelledby="priorities-title" className="dash-priorities">
        <div className="dash-section-heading">
          <h2 id="priorities-title">Da gestire</h2>
          <span>Scadenze e attenzione operativa</span>
        </div>
        <div className="dash-priority-grid">
          <a
            href="#dashboard-billings"
            onClick={() => setBillingScope("ARRETRATA")}
            className={overdue ? "dash-priority is-warning" : "dash-priority"}
          >
            <span>Fatturazioni arretrate</span>
            <strong>
              {overdue ?? "—"}
              <ArrowRight size={17} />
            </strong>
            <small>Previste nei mesi precedenti</small>
          </a>
          <a
            href="#dashboard-effort"
            className={ops?.progetti_superati.length ? "dash-priority is-danger" : "dash-priority"}
          >
            <span>Progetti oltre budget</span>
            <strong>
              {ops?.progetti_superati.length ?? "—"}
              <ArrowRight size={17} />
            </strong>
            <small>Consumo superiore alle giornate previste</small>
          </a>
          <Link
            to="/wallet"
            className={
              Number(walletData?.residui_in_scadenza) > 0
                ? "dash-priority is-warning"
                : "dash-priority"
            }
          >
            <span>Residui in scadenza</span>
            <strong>
              {walletData ? formatDays(walletData.residui_in_scadenza) : "—"}
              <ArrowRight size={17} />
            </strong>
            <small>Giornate da utilizzare entro la scadenza</small>
          </Link>
          <Link
            to="/revisione"
            className={
              Number(walletData?.residui_potenziali_da_verificare) > 0
                ? "dash-priority is-warning"
                : "dash-priority"
            }
          >
            <span>Residui da verificare</span>
            <strong>
              {walletData ? formatDays(walletData.residui_potenziali_da_verificare) : "—"}
              <ArrowRight size={17} />
            </strong>
            <small>Da validare prima di renderli disponibili</small>
          </Link>
        </div>
      </section>
      <div className="dash-main-grid">
        <section id="dashboard-billings" className="dash-panel">
          <div className="dash-section-heading">
            <div>
              <p className="dash-eyebrow">SCADENZE</p>
              <h2>Fatturazioni da gestire</h2>
            </div>
            <span>{billings?.count ?? "—"} aperte</span>
          </div>
          <div className="dash-tabs" role="group" aria-label="Periodo fatturazioni">
            {[
              ["all", "Tutte"],
              ["MESE_CORRENTE", "Mese corrente"],
              ["ARRETRATA", "Arretrate"],
            ].map(([value, label]) => (
              <button
                key={value}
                aria-pressed={billingScope === value}
                onClick={() => setBillingScope(value!)}
              >
                {label}
              </button>
            ))}
          </div>
          {dashboard.isLoading ? (
            <Loading />
          ) : dashboard.isError ? (
            <p className="dash-muted">Fatturazioni non disponibili.</p>
          ) : visibleBillings.length ? (
            <div className="dash-billing-list">
              {visibleBillings.map((item) => (
                <Link className="dash-billing" key={item.id} to={`/progetti/${item.progetto_id}`}>
                  <div className="dash-billing-title">
                    <strong>{item.progetto_titolo || item.progetto_codice}</strong>
                    <span>{item.progetto_codice}</span>
                  </div>
                  <div className="dash-billing-date">
                    <span
                      className={
                        item.classificazione === "ARRETRATA"
                          ? "dash-badge is-warning"
                          : "dash-badge"
                      }
                    >
                      {item.classificazione === "ARRETRATA" ? "Arretrata" : "Questo mese"}
                    </span>
                    <time>
                      {new Intl.DateTimeFormat("it-IT", { timeZone: "UTC" }).format(
                        new Date(item.data_pianificata),
                      )}
                    </time>
                  </div>
                  <ArrowUpRight size={16} />
                </Link>
              ))}
            </div>
          ) : (
            <p className="dash-empty">
              {billingScope === "all"
                ? t("dashboard.noUpcomingBillings")
                : "Nessuna fatturazione nell'elenco per questo periodo."}
            </p>
          )}
          {billings && (
            <p className="dash-caption mt-3">
              {visibleBillings.length} visualizzate / {billings.count} totali.{" "}
              {billings.count > billings.limit
                ? `Elenco limitato alle prime ${billings.limit} scadenze; i filtri agiscono su queste righe.`
                : "Mese corrente e arretrati ancora aperti."}
            </p>
          )}
        </section>
        <section id="dashboard-effort" className="dash-panel">
          <div className="dash-section-heading">
            <div>
              <p className="dash-eyebrow">EFFORT</p>
              <h2>Capacità e disponibilità</h2>
            </div>
          </div>
          <div className="dash-capacity dash-violet">
            <div>
              <strong>Organico allargato</strong>
              <Link to="/canone" aria-label="Apri organico allargato">
                <ArrowUpRight size={17} />
              </Link>
            </div>
            <dl>
              <div>
                <dt>Monte non ancora allocato</dt>
                <dd>{ops ? formatDays(ops.organico.non_allocato) : "—"}</dd>
              </div>
              <div>
                <dt>Allocato ancora da consumare</dt>
                <dd>
                  {ops
                    ? formatDays(Number(ops.organico.allocato) - Number(ops.organico.consumato))
                    : "—"}
                </dd>
              </div>
            </dl>
            <p className="dash-caption">Il consumo include le attività completate del periodo.</p>
          </div>
          <div className="dash-capacity dash-cyan">
            <div>
              <strong>Wallet {year}</strong>
              <Link to="/wallet" aria-label="Apri disponibilità wallet">
                <ArrowUpRight size={17} />
              </Link>
            </div>
            <dl>
              {[
                ["Disponibile sulle allocazioni", walletData?.disponibile],
                ["Residui validi non allocati", walletData?.residui_validi_non_allocati],
                ["Residui scaduti", walletData?.residui_scaduti],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value === undefined ? "—" : formatDays(value)}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="dash-capacity dash-blue">
            <div>
              <strong>Progetti in corso</strong>
              <Link to="/progetti" aria-label="Apri progetti">
                <ArrowUpRight size={17} />
              </Link>
            </div>
            <dl>
              <div>
                <dt>Budget residuo operativo</dt>
                <dd>
                  {walletData ? formatDays(walletData.budget_residuo_progetti_in_corso) : "—"}
                </dd>
              </div>
            </dl>
            <p className="dash-caption">Al netto delle giornate rilasciate al wallet.</p>
            {!!ops?.progetti_superati.length && (
              <details className="dash-overruns">
                <summary>{ops.progetti_superati.length} progetti oltre budget</summary>
                <ul>
                  {ops.progetti_superati.map((x) => (
                    <li key={x.id}>
                      <Link to={`/progetti/${x.id}`}>
                        {x.titolo}
                        <span>+{formatDays(x.sforamento)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        </section>
      </div>
      <section className="dash-panel" aria-labelledby="referent-distribution-title">
        <div className="dash-section-heading">
          <div>
            <p className="dash-eyebrow">DISTRIBUZIONE DEL LAVORO</p>
            <h2 id="referent-distribution-title">Distribuzione per referente BMED</h2>
          </div>
          <div className="dash-controls">
            <div className="dash-tabs" role="group" aria-label="Perimetro referenti">
              {[
                ["active", "In corso"],
                ["all", "Tutti"],
              ].map(([value, label]) => (
                <button key={value} aria-pressed={scope === value} onClick={() => setScope(value!)}>
                  {label}
                </button>
              ))}
            </div>
            <div className="dash-tabs" role="group" aria-label="Metrica referenti">
              {[
                ["count", "Numero attività"],
                ["days", "Giornate previste"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  aria-pressed={measure === value}
                  onClick={() => setMeasure(value!)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <p className="dash-caption">
          {scope === "active"
            ? "Progetti attivi e attività con allocazioni wallet aperte, su tutti gli anni."
            : "Tutti gli stati e tutti gli anni."}{" "}
          Le attività tecniche sono escluse. Le giornate sono previste o assegnate, non
          consuntivate.
        </p>
        {dashboard.isLoading ? (
          <Loading />
        ) : dashboard.isError ? (
          <p className="dash-empty">Distribuzione non disponibile.</p>
        ) : !referents.length ? (
          <p className="dash-empty">Nessun progetto o attività wallet disponibile.</p>
        ) : (
          <Tooltip.Provider delayDuration={150}>
            <ul className="dash-referents">
              {referents.map((row) => (
                <li key={row.referente_id ?? "unassigned"}>
                  <span>{row.referente}</span>
                  <Tooltip.Root>
                    <Tooltip.Trigger asChild>
                      <button
                        className="dash-referent-bar"
                        aria-label={`${row.referente}: ${measure === "count" ? "Progetti e attivita wallet" : "Giornate previste"}, ${score(row)}. Mostra dettaglio`}
                      >
                        <span className="dash-track" aria-hidden="true">
                          <span style={{ width: `${(score(row) / max) * 100}%` }} />
                        </span>
                        <strong>
                          {measure === "days" ? formatDays(row.monte_giornate) : score(row)}
                        </strong>
                      </button>
                    </Tooltip.Trigger>
                    <Tooltip.Portal>
                      <Tooltip.Content
                        sideOffset={8}
                        collisionPadding={12}
                        className="dash-referent-tooltip"
                      >
                        <strong>{row.referente}</strong>
                        <dl>
                          <div>
                            <dt>Progetti</dt>
                            <dd>{row.progetti}</dd>
                          </div>
                          <div>
                            <dt>Wallet</dt>
                            <dd>{row.attivita_wallet}</dd>
                          </div>
                          <div>
                            <dt>Monte GG gestite</dt>
                            <dd>{formatDays(row.monte_giornate)}</dd>
                          </div>
                        </dl>
                        <Tooltip.Arrow className="fill-card" />
                      </Tooltip.Content>
                    </Tooltip.Portal>
                  </Tooltip.Root>
                </li>
              ))}
            </ul>
          </Tooltip.Provider>
        )}
      </section>
      <div className="dash-bottom-grid">
        <section aria-label="Stati dei progetti">
          <DonutChart
            title={t("dashboard.projectsByStatus")}
            data={projectChart}
            premium
            caption="Portafoglio complessivo, tutti gli stati e tutti gli anni."
          />
        </section>
        <section className="dash-panel">
          <div className="dash-section-heading">
            <div>
              <p className="dash-eyebrow">CONFRONTO FORNITORE</p>
              <h2>Riconciliazione</h2>
            </div>
            <Link to="/riconciliazione" aria-label="Apri riconciliazione">
              <ArrowUpRight size={18} />
            </Link>
          </div>
          {reconciliation.isLoading ? (
            <Loading />
          ) : reconciliation.isError || !recon ? (
            <p className="dash-empty">Dati di riconciliazione non disponibili.</p>
          ) : (
            <>
              <div className="dash-reconciliation">
                <strong>
                  {recon.delta_totale === null
                    ? "Non disponibile"
                    : formatDelta(recon.delta_totale)}
                </strong>
                <span>Scostamento giornate rispetto al fornitore</span>
              </div>
              <p
                className={`dash-badge ${recon.stato === "NON_ALLINEATO" ? "is-danger" : recon.stato === "PARZIALE" ? "is-warning" : ""}`}
              >
                {recon.stato === "NON_VERIFICABILE"
                  ? "Non verificabile / dati assenti"
                  : recon.stato === "ALLINEATO"
                    ? "Dati allineati"
                    : recon.stato === "PARZIALE"
                      ? "Confronto parziale"
                      : "Scostamenti da verificare"}
              </p>
              <div className="dash-recon-counts">
                <div>
                  <strong>{recon.ok}</strong>
                  <span>Righe allineate</span>
                </div>
                <div>
                  <strong>{recon.ko}</strong>
                  <span>Da verificare</span>
                </div>
                <div>
                  <strong>{recon.assenti_in_ppm}</strong>
                  <span>Assenti in PPM</span>
                </div>
              </div>
              <p className="dash-caption">
                {formatPercent(recon.percentuale_allineati)} allineati / {recon.righe} righe. Ultimo
                estratto:{" "}
                {recon.snapshot_estratto_il
                  ? new Date(recon.snapshot_estratto_il).toLocaleDateString("it-IT")
                  : "non disponibile"}
                .
              </p>
            </>
          )}
        </section>
      </div>
    </section>
  );
}
