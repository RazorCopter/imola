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
};
const num = (value: number | string) =>
  new Intl.NumberFormat("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(
    Number(value),
  );
const sum = <T,>(items: T[], value: (item: T) => string) =>
  items.reduce((total, item) => total + Number(value(item)), 0);
const ratio = (part: number, total: number) => (total > 0 ? `${num((part / total) * 100)}%` : "—");
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
function Table({ headings, rows }: { headings: string[]; rows: (string | number)[][] }) {
  return rows.length ? (
    <table>
      <thead>
        <tr>
          {headings.map((heading) => (
            <th key={heading}>{heading}</th>
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
  ) : (
    <p className="report-empty">Nessun dato nel perimetro selezionato.</p>
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
  const or = sum(data.domains, (x) => x.reserved),
    oc = sum(data.domains, (x) => x.consumed);
  const cards = [
    [
      "Progetti attivi",
      String(data.projects.length),
      `${num(pc)} / ${num(pb)} gg`,
      `Effort consumato ${ratio(pc, pb)}`,
    ],
    [
      "Wallet aperto",
      String(new Set(data.wallet.map((x) => x.code)).size),
      `${num(wc)} / ${num(wa)} gg`,
      `Giornate consumate ${ratio(wc, wa)}`,
    ],
    [
      "Organico allargato",
      String(data.activities.length),
      `${num(oc)} / ${num(or)} gg`,
      `Riservato eroso ${ratio(oc, or)}`,
    ],
  ];
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
            <p>SUPPLIER LEDGER / SINTESI DIREZIONALE</p>
            <h1>
              Gestione fornitori
              <br />e progetti
            </h1>
            <div className="report-rule" />
            <p>Quadro operativo di progetti, wallet e Organico Allargato</p>
          </div>
          <div className="report-kpis">
            {cards.map(([title, count, detail, percent]) => (
              <article key={title}>
                <span>{title}</span>
                <strong>{count}</strong>
                <p>{detail}</p>
                <small>{percent}</small>
              </article>
            ))}
          </div>
          <div className="report-domain">
            <h2>Organico Allargato · distribuzione per dominio</h2>
            <Table
              headings={["Dominio", "Attività", "Riservate", "Erose", "Da erodere"]}
              rows={data.domains.map((x) => [
                x.domain,
                x.count,
                num(x.reserved),
                num(x.consumed),
                num(x.remaining),
              ])}
            />
          </div>
          <p className="report-footnote">
            Dati al {data.date.split("-").reverse().join("/")}. Progetti attivi; allocazioni wallet
            aperte non tecniche; attività dei canoni nel periodo corrente. I valori sono espressi in
            giornate. Progetti e wallet sono ambiti distinti e non vengono sommati.
          </p>
        </section>
        <section className="report-details">
          <Masthead date={data.date} />
          <h2>01 / Progetti in corso</h2>
          <p>Effort previsto e consumo totale, inclusa l'eventuale quota wallet.</p>
          <Table
            headings={[
              "Progetto",
              "Referente BMED",
              "Fine prevista",
              "Budget gg",
              "Consumo gg",
              "%",
            ]}
            rows={data.projects.map((x) => [
              `${x.code} · ${x.title}`,
              x.owner || "Non assegnato",
              x.end || "—",
              num(x.budget),
              num(x.consumed),
              ratio(Number(x.consumed), Number(x.budget)),
            ])}
          />
          <h2>02 / Attività wallet in corso</h2>
          <p>Una riga per allocazione aperta; le attività possono avere più allocazioni.</p>
          <Table
            headings={["Attività", "Referente BMED", "Anno", "Riservate", "Erose", "Residue"]}
            rows={data.wallet.map((x) => [
              `${x.code} · ${x.title}`,
              x.owner || "Non assegnato",
              x.year,
              num(x.allocated),
              num(x.consumed),
              num(x.remaining),
            ])}
          />
          <h2>03 / Attività Organico Allargato</h2>
          <p>Attività dei canoni il cui periodo include la data del report.</p>
          <Table
            headings={["Dominio", "Attività", "Periodo", "Riservate", "Erose", "Residue"]}
            rows={data.activities.map((x) => [
              x.domain,
              x.title,
              x.period,
              num(x.reserved),
              num(x.consumed),
              num(x.remaining),
            ])}
          />
        </section>
      </main>
    </div>
  );
}
