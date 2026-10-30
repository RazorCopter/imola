import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import "./report.css";

type Project = {
  code: string;
  title: string;
  owner: string | null;
  budget: string;
  consumed: string;
  end: string | null;
};
type Wallet = {
  code: string;
  title: string;
  owner: string | null;
  assignee: string | null;
  year: number;
  allocated: string;
  consumed: string;
  remaining: string;
};
type Activity = {
  domain: string;
  title: string;
  period: string;
  reserved: string;
  consumed: string;
  remaining: string;
};
type Domain = {
  domain: string;
  count: number;
  reserved: string;
  consumed: string;
  remaining: string;
};
type Report = {
  date: string;
  projects: Project[];
  wallet: Wallet[];
  domains: Domain[];
  activities: Activity[];
  organico_monte: string;
  economics: {
    kpi: { total_cost: string; daily_person_cost: string };
    by_source: { source: string; cost: string }[];
    monthly_trend: { month: string; cost: string }[];
  };
};
const num = (value: number | string) =>
  new Intl.NumberFormat("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(
    Number(value),
  );
const sum = <T,>(items: T[], value: (item: T) => string) =>
  items.reduce((total, item) => total + Number(value(item)), 0);
const ratio = (part: number, total: number) => (total > 0 ? `${num((part / total) * 100)}%` : "—");
const euro = (value: number | string) =>
  new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(Number(value));
function Gauge({ consumed, total }: { consumed: number; total: number }) {
  const percent = total > 0 ? (consumed / total) * 100 : 0;
  return (
    <svg
      className="report-gauge"
      viewBox="0 0 120 120"
      role="img"
      aria-label={`Consumo ${ratio(consumed, total)}`}
    >
      <circle cx="60" cy="60" r="48" fill="none" stroke="#e3eaf3" strokeWidth="9" />
      <circle
        cx="60"
        cy="60"
        r="48"
        fill="none"
        stroke={percent > 100 ? "#c65736" : "currentColor"}
        strokeWidth="9"
        strokeLinecap="round"
        pathLength="100"
        strokeDasharray={`${Math.min(100, Math.max(0, percent))} 100`}
        transform="rotate(-90 60 60)"
      />
      <text x="60" y="62" textAnchor="middle" className="report-gauge-value">
        {total > 0 ? `${Math.round(percent)}%` : "N/D"}
      </text>
      <text x="60" y="78" textAnchor="middle" className="report-gauge-label">
        CONSUMO
      </text>
    </svg>
  );
}
function CostTrend({
  data,
  date,
  available,
}: {
  data: Report["economics"]["monthly_trend"];
  date: string;
  available: boolean;
}) {
  const months = [
    "Gen",
    "Feb",
    "Mar",
    "Apr",
    "Mag",
    "Giu",
    "Lug",
    "Ago",
    "Set",
    "Ott",
    "Nov",
    "Dic",
  ];
  const current = Number(date.slice(5, 7));
  const values = months
    .slice(0, current)
    .map((_, i) =>
      Number(
        data.find((x) => x.month === `${date.slice(0, 4)}-${String(i + 1).padStart(2, "0")}`)
          ?.cost ?? 0,
      ),
    );
  const low = Math.min(0, ...values),
    high = Math.max(1, ...values);
  const y = (v: number) => 110 - ((v - low) / (high - low)) * 85;
  const points = values.map((v, i) => `${36 + i * 48},${y(v)}`);
  if (!available)
    return (
      <p className="report-empty">Imposta la tariffa giornaliera per valorizzare i consuntivi.</p>
    );
  return (
    <svg
      className="report-trend"
      viewBox="0 0 610 150"
      role="img"
      aria-label="Costo mensile maturato su progetti e wallet, da gennaio alla data del report"
    >
      {[0, 0.5, 1].map((t) => (
        <g key={t}>
          <line
            x1="30"
            x2="585"
            y1={25 + t * 85}
            y2={25 + t * 85}
            stroke="#e4ebf4"
            strokeDasharray="3 4"
          />
          <text x="585" y={20 + t * 85} textAnchor="end" fontSize="9" fill="#62718d">
            {euro(high - t * (high - low))}
          </text>
        </g>
      ))}
      <polygon
        points={`${36},${y(0)} ${points.join(" ")} ${36 + (values.length - 1) * 48},${y(0)}`}
        fill="#d9f0fb"
        opacity="0.65"
      />
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke="#198fc8"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      {values.map((v, i) => (
        <g key={i}>
          <circle cx={36 + i * 48} cy={y(v)} r="4" fill="#fff" stroke="#198fc8" strokeWidth="2">
            <title>
              {months[i]}: {euro(v)}
            </title>
          </circle>
          <text x={36 + i * 48} y="137" textAnchor="middle" fontSize="11" fill="#526581">
            {months[i]}
          </text>
        </g>
      ))}
    </svg>
  );
}
function Masthead({ date }: { date: string }) {
  return (
    <header className="report-masthead">
      <img src="/banca-mediolanum.svg" alt="Banca Mediolanum" />
      <div>
        <strong>ARCHITETTURE IT</strong>
        <span>REPORT GESTIONALE · {date.split("-").reverse().join("/")}</span>
      </div>
    </header>
  );
}
function Table({ headings, rows }: { headings: string[]; rows: ReactNode[][] }) {
  return rows.length ? (
    <div className="report-table-scroll">
      <table>
        <thead>
          <tr>
            {headings.map((heading) => (
              <th scope="col" key={heading}>
                {heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {row.map((cell, i) => (
                <td key={i}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <p className="report-empty">Nessun dato nel perimetro selezionato.</p>
  );
}
function Effort({ consumed, total }: { consumed: string; total: string }) {
  const used = Number(consumed),
    budget = Number(total);
  const state =
    used > budget
      ? "Superato"
      : budget > 0 && used === budget
        ? "Esaurito"
        : budget === 0
          ? "Non definito"
          : "Disponibile";
  const tone = used > budget ? "over" : budget > 0 && used === budget ? "full" : "normal";
  return (
    <div className={`report-effort report-effort-${tone}`}>
      <div className="report-effort-label">
        <strong>{ratio(used, budget)}</strong>
        <span>{state}</span>
      </div>
      <div className="report-effort-track" aria-hidden="true">
        <div
          style={{
            width: `${budget > 0 ? Math.min(100, Math.max(0, (used / budget) * 100)) : used > 0 ? 100 : 0}%`,
          }}
        />
      </div>
    </div>
  );
}
function Identity({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="report-identity">
      <strong>{title}</strong>
      <span>{subtitle}</span>
    </div>
  );
}
function DetailSection({
  date,
  number,
  title,
  description,
  tone,
  metrics,
  children,
}: {
  date: string;
  number: string;
  title: string;
  description: string;
  tone: string;
  metrics: { label: string; value: string }[];
  children: ReactNode;
}) {
  return (
    <section className={`report-details report-detail-${tone}`}>
      <Masthead date={date} />
      <div className="report-section-heading">
        <span>{number}</span>
        <div>
          <p>DETTAGLIO OPERATIVO</p>
          <h2>{title}</h2>
        </div>
      </div>
      <p className="report-section-description">{description}</p>
      <div className="report-section-metrics">
        {metrics.map((metric) => (
          <div key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </div>
      {children}
      <footer className="report-section-footer">
        <strong>ARCHITETTURE IT</strong>
        <span>
          {title} / Dati al {date.split("-").reverse().join("/")}
        </span>
      </footer>
    </section>
  );
}
export function ManagementReportPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["management-report"],
    queryFn: () => api.get<Report>("/admin/management-report"),
  });
  if (isLoading) return <p className="report-loading">Caricamento report...</p>;
  if (isError || !data)
    return (
      <div className="report-loading">
        <p>Impossibile caricare il report.</p>
        <button onClick={() => void refetch()}>Riprova</button>{" "}
        <Link to="/">Torna alla dashboard</Link>
      </div>
    );
  const pb = sum(data.projects, (x) => x.budget),
    pc = sum(data.projects, (x) => x.consumed);
  const wa = sum(data.wallet, (x) => x.allocated),
    wc = sum(data.wallet, (x) => x.consumed);
  const organicoMonte = Number(data.organico_monte),
    oc = sum(data.domains, (x) => x.consumed),
    organicoAllocato = sum(data.domains, (x) => x.reserved);
  const economics = data.economics;
  const priced = Number(economics.kpi.daily_person_cost) > 0;
  const cost = (source: string) =>
    economics.by_source.find((x) => x.source === source)?.cost ?? "0";
  const cards = [
    {
      title: "Progetti attivi",
      count: data.projects.length,
      consumed: pc,
      total: pb,
      label: "giornate di budget",
      color: "blue",
    },
    {
      title: "Attività wallet",
      count: new Set(data.wallet.map((x) => x.code)).size,
      consumed: wc,
      total: wa,
      label: "giornate riservate",
      color: "cyan",
    },
    {
      title: "Organico allargato",
      count: data.activities.length,
      consumed: oc,
      total: organicoMonte,
      label: "giornate del monte",
      color: "violet",
    },
  ];
  const attention = data.projects.filter(
    (x) => Number(x.consumed) >= Number(x.budget) && Number(x.budget) > 0,
  ).length;
  return (
    <div className="report-shell">
      <div className="report-actions">
        <Link to="/">← Dashboard</Link>
        <button onClick={() => window.print()}>Stampa / Salva PDF</button>
      </div>
      <main className="report-document">
        <section className="report-cover">
          <Masthead date={data.date} />
          <div className="report-title">
            <div>
              <p>EXECUTIVE OVERVIEW / {data.date.slice(0, 4)}</p>
              <h1>
                Fornitori e progetti<span>Il quadro della gestione.</span>
              </h1>
              <p>Portafoglio, effort e valorizzazione economica</p>
            </div>
            <div className="report-edition">
              <strong>
                {new Intl.DateTimeFormat("it-IT", { month: "long", timeZone: "UTC" }).format(
                  new Date(data.date),
                )}
              </strong>
              <span>{data.date.slice(0, 4)} / ARCHITETTURE IT</span>
            </div>
          </div>
          <div className="report-finance">
            <div className="report-finance-total">
              <span>COSTO MATURATO / ANNO IN CORSO</span>
              <strong>{priced ? euro(economics.kpi.total_cost) : "Non disponibile"}</strong>
              <p>Progetti + wallet · dal 1 gennaio</p>
              <small>Valorizzazione dei consuntivi, non fatturato</small>
            </div>
            <div className="report-finance-split">
              <div>
                <span>Consuntivi diretti progetti</span>
                <strong>{priced ? euro(cost("PROJECT")) : "N/D"}</strong>
              </div>
              <div>
                <span>Consuntivi wallet</span>
                <strong>{priced ? euro(cost("WALLET")) : "N/D"}</strong>
              </div>
              <small>
                Tariffa corrente: {euro(economics.kpi.daily_person_cost)} / gg · Canoni esclusi
              </small>
            </div>
          </div>
          <article className="report-chart-panel">
            <div className="report-panel-heading">
              <h2>Andamento economico</h2>
              <span>COSTO MENSILE · EUR</span>
            </div>
            <CostTrend data={economics.monthly_trend} date={data.date} available={priced} />
          </article>
          <div className="report-kpis">
            {cards.map((card) => (
              <article key={card.title} className={`report-kpi-${card.color}`}>
                <span>{card.title}</span>
                <div className="report-kpi-main">
                  <div>
                    <strong>{card.count}</strong>
                    <small>in corso</small>
                  </div>
                  <Gauge consumed={card.consumed} total={card.total} />
                </div>
                <p>
                  {num(card.consumed)} <span>/ {num(card.total)} gg</span>
                </p>
                <small>{card.label}</small>
              </article>
            ))}
          </div>
          <div className="report-domain report-chart-panel">
            <div className="report-panel-heading">
              <h2>Organico allargato / domini</h2>
              <span>EROSO / RISERVATO · GG</span>
            </div>
            <div className="report-domain-bars">
              {data.domains.length ? (
                data.domains.map((x) => (
                  <div className="report-domain-row" key={x.domain}>
                    <strong>{x.domain}</strong>
                    <div className="report-domain-track">
                      <div
                        style={{
                          width: `${Math.min(100, Math.max(0, (Number(x.consumed) / (Number(x.reserved) || 1)) * 100))}%`,
                        }}
                      />
                    </div>
                    <span>
                      {num(x.consumed)} / {num(x.reserved)}
                    </span>
                  </div>
                ))
              ) : (
                <p className="report-empty">Nessun dominio nel periodo corrente.</p>
              )}
            </div>
          </div>
          <div className="report-insights">
            <div>
              <strong>{attention}</strong>
              <span>progetti con budget esaurito o superato</span>
            </div>
            <div>
              <strong>{num(organicoMonte - oc)} gg</strong>
              <span>monte organico ancora disponibile</span>
            </div>
            <div>
              <strong>{num(organicoMonte - organicoAllocato)} gg</strong>
              <span>monte non ancora allocato</span>
            </div>
            <div>
              <strong>{num(organicoAllocato - oc)} gg</strong>
              <span>allocato e ancora da consumare</span>
            </div>
            <div>
              <strong>{data.projects.filter((x) => !x.owner).length}</strong>
              <span>progetti senza referente BMED</span>
            </div>
          </div>
          <p className="report-footnote">
            Dati al {data.date.split("-").reverse().join("/")}. Progetti attivi; allocazioni wallet
            aperte non tecniche; dettaglio delle sole attività in corso dei canoni nel periodo
            corrente. I KPI e i domini includono i consumi delle attività chiuse. I valori sono
            espressi in giornate. Gli effort di progetti e wallet non sono sommati. I costi annuali
            includono i consuntivi anche di progetti chiusi, al netto degli storni, alla tariffa
            corrente non storicizzata; non sono importi fatturati o pagati. Il monte disponibile
            comprende la quota non allocata e quella allocata ma non ancora consumata.
          </p>
        </section>
        <DetailSection
          date={data.date}
          number="01"
          title="Progetti in corso"
          tone="blue"
          description="Effort previsto e consumo totale, inclusa l'eventuale quota wallet. Gli indicatori descrivono la disponibilità del budget, non lo stato di fatturazione."
          metrics={[
            { label: "Progetti attivi", value: String(data.projects.length) },
            { label: "Budget complessivo", value: `${num(pb)} gg` },
            { label: "Effort consumato", value: `${num(pc)} gg` },
            { label: "Consumo del budget", value: ratio(pc, pb) },
          ]}
        >
          <Table
            headings={[
              "Progetto / fine prevista",
              "Referente BMED",
              "Budget gg",
              "Consumo gg",
              "Consumo budget",
            ]}
            rows={data.projects.map((x) => [
              <Identity
                title={x.title}
                subtitle={`${x.code} / Fine: ${x.end ? x.end.split("-").reverse().join("/") : "Non definita"}`}
              />,
              x.owner || "Non assegnato",
              num(x.budget),
              num(x.consumed),
              <Effort consumed={x.consumed} total={x.budget} />,
            ])}
          />
        </DetailSection>
        <DetailSection
          date={data.date}
          number="02"
          title="Attività wallet in corso"
          tone="cyan"
          description="Allocazioni aperte non tecniche. Una riga per allocazione: la stessa attività può comparire su più annualità. Le giornate residue restano visibili anche in caso di superamento."
          metrics={[
            {
              label: "Attività / allocazioni",
              value: `${new Set(data.wallet.map((x) => x.code)).size} / ${data.wallet.length}`,
            },
            { label: "Giornate riservate", value: `${num(wa)} gg` },
            { label: "Giornate erose", value: `${num(wc)} gg` },
            { label: "Giornate residue", value: `${num(sum(data.wallet, (x) => x.remaining))} gg` },
          ]}
        >
          <Table
            headings={[
              "Attività / annualità",
              "Assegnatario",
              "Riservate gg",
              "Erose / residue gg",
              "Consumo riserva",
            ]}
            rows={data.wallet.map((x) => [
              <Identity title={x.title} subtitle={`${x.code} / ${x.year}`} />,
              x.assignee || x.owner || "Non assegnato",
              num(x.allocated),
              <Identity title={num(x.consumed)} subtitle={`${num(x.remaining)} residue`} />,
              <Effort consumed={x.consumed} total={x.allocated} />,
            ])}
          />
        </DetailSection>
        <DetailSection
          date={data.date}
          number="03"
          title="Organico allargato"
          tone="violet"
          description="Solo attività in corso dei canoni nel periodo corrente. I totali di questa sezione riguardano le righe elencate; la sintesi iniziale include anche i consumi delle attività completate."
          metrics={[
            { label: "Attività in corso", value: String(data.activities.length) },
            {
              label: "Giornate riservate",
              value: `${num(sum(data.activities, (x) => x.reserved))} gg`,
            },
            {
              label: "Giornate erose",
              value: `${num(sum(data.activities, (x) => x.consumed))} gg`,
            },
            { label: "Da erodere", value: `${num(sum(data.activities, (x) => x.remaining))} gg` },
          ]}
        >
          <Table
            headings={[
              "Attività / periodo",
              "Dominio",
              "Riservate gg",
              "Erose / residue gg",
              "Consumo riserva",
            ]}
            rows={data.activities.map((x) => [
              <Identity title={x.title} subtitle={x.period} />,
              x.domain,
              num(x.reserved),
              <Identity title={num(x.consumed)} subtitle={`${num(x.remaining)} residue`} />,
              <Effort consumed={x.consumed} total={x.reserved} />,
            ])}
          />
        </DetailSection>
      </main>
    </div>
  );
}
