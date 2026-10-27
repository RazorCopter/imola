import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CostAnalysisPage } from "../CostAnalysisPage";
import { ChartTooltip } from "@/components/AccessibleBarChart";
import { api } from "@/lib/api";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) =>
      ({
        "costAnalysis.title": "Analisi Costi",
        "costAnalysis.from": "Dal",
        "costAnalysis.to": "Al",
        "costAnalysis.apply": "Applica filtri",
        "costAnalysis.zeroCost": "Il costo giornata uomo non è valorizzato.",
        "costAnalysis.empty": "Nessun consuntivo nel periodo selezionato.",
        "costAnalysis.error": "Analisi costi non disponibile",
        "costAnalysis.projectChart": "Costi per progetto",
        "costAnalysis.projectChartDescription": "Progetti ordinati per costo decrescente.",
        "costAnalysis.projectSearch": "Cerca progetto",
        "costAnalysis.projectLimit": "Numero di progetti",
        "costAnalysis.projectChartSummary": "Riepilogo costi per progetto",
        "costAnalysis.noMatchingProjects": "Nessun progetto corrisponde alla ricerca.",
        "costAnalysis.label": "Voce",
        "costAnalysis.cost": "Costo",
      })[key] ?? key,
  }),
}));
vi.mock("@/lib/api", () => ({ api: { get: vi.fn() } }));
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  BarChart: ({ children, data }: { children: React.ReactNode; data: { label?: string }[] }) => (
    <div data-testid="bar-chart" data-labels={data.map((row) => row.label).join("|")}>
      {children}
    </div>
  ),
  Bar: () => null,
  CartesianGrid: () => null,
  Legend: () => null,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

function renderPage() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <CostAnalysisPage />
    </QueryClientProvider>,
  );
}

const payload = {
  policy: "Costo globale corrente.",
  kpi: { total_days: "2.0000", total_cost: "0.00", daily_person_cost: "0.00" },
  by_project: [{ label: "P1 — Progetto", days: "2.0000", cost: "0.00" }],
  by_supplier: [{ label: "Fornitore", days: "2.0000", cost: "0.00" }],
  by_source: [{ source: "PROJECT", days: "2.0000", cost: "0.00" }],
  monthly_trend: [{ month: "2026-01", days: "2.0000", cost: "0.00" }],
};

describe("CostAnalysisPage", () => {
  beforeEach(() => vi.clearAllMocks());
  it("mostra KPI, grafico, tabelle, avviso costo zero e applica filtri", async () => {
    vi.mocked(api.get).mockResolvedValue(payload);
    renderPage();
    expect(await screen.findByText("Analisi Costi")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("non è valorizzato");
    expect(screen.getByTestId("bar-chart")).toBeInTheDocument();
    expect(screen.getAllByText("P1 — Progetto")).toHaveLength(2);
    await userEvent.type(screen.getByLabelText("Dal"), "2026-01-01");
    await userEvent.click(screen.getByRole("button", { name: "Applica filtri" }));
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith("/cost-analysis?from=2026-01-01"));
  });
  it("gestisce empty ed errore", async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ ...payload, by_project: [] });
    const view = renderPage();
    expect(
      await screen.findByText("Nessun consuntivo nel periodo selezionato."),
    ).toBeInTheDocument();
    view.unmount();
    vi.mocked(api.get).mockRejectedValueOnce(new Error("boom"));
    renderPage();
    expect(await screen.findByText("Analisi costi non disponibile")).toBeInTheDocument();
  });
  it("ordina per costo, applica Top N e ricerca senza modificare i KPI", async () => {
    const projects = Array.from({ length: 12 }, (_, index) => ({
      label: `Progetto ${String(index + 1).padStart(2, "0")}`,
      days: "1.0000",
      cost: String((index + 1) * 100),
    }));
    vi.mocked(api.get).mockResolvedValue({ ...payload, by_project: projects });
    const user = userEvent.setup();
    renderPage();

    const chart = await screen.findByTestId("bar-chart");
    expect(chart).toHaveAttribute(
      "data-labels",
      projects
        .slice()
        .reverse()
        .slice(0, 10)
        .map((row) => row.label)
        .join("|"),
    );
    expect(screen.getAllByText((content) => content.includes("0,00"))).not.toHaveLength(0);

    await user.selectOptions(screen.getByLabelText("Numero di progetti"), "5");
    expect(chart).toHaveAttribute(
      "data-labels",
      "Progetto 12|Progetto 11|Progetto 10|Progetto 09|Progetto 08",
    );

    await user.type(screen.getByLabelText("Cerca progetto"), "03");
    expect(chart).toHaveAttribute("data-labels", "Progetto 03");
    const summary = screen.getByRole("table", { name: "Riepilogo costi per progetto" });
    expect(within(summary).getByText("Progetto 03")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Cerca progetto"));
    await user.type(screen.getByLabelText("Cerca progetto"), "inesistente");
    expect(screen.getByText("Nessun progetto corrisponde alla ricerca.")).toBeInTheDocument();
  });

  it("usa un tooltip custom opaco, leggibile e completo", () => {
    render(
      <ChartTooltip
        active
        label="PRJ-01 — Nome progetto completo"
        unit="euro"
        payload={[{ name: "Costo", value: 1234.5, color: "#6366f1" }]}
      />,
    );

    const tooltip = screen.getByTestId("chart-tooltip");
    expect(tooltip).toHaveStyle({ backgroundColor: "#0f172a", color: "#f8fafc", opacity: "1" });
    expect(tooltip).toHaveClass("border-slate-600", "shadow-2xl");
    expect(screen.getByText("PRJ-01 — Nome progetto completo")).toHaveClass("break-words");
    expect(screen.getByText("Costo")).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes("1234,50"))).toBeInTheDocument();
  });
});
