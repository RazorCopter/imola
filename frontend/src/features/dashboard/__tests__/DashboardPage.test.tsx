import "@/i18n";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { DashboardPage } from "../DashboardPage";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn() } }));
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PieChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Pie: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Cell: () => null,
  Tooltip: () => null,
}));

const getMock = vi.mocked(api.get);

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const wallet = {
  anno: 2026,
  allocato: "10.0000",
  consumato: "4.0000",
  disponibile: "6.0000",
  disponibile_da_allocazioni: "6.0000",
  disponibile_da_allocazioni_aperte: "6.0000",
  capienza_wallet_potenziale: "6.0000",
  residui_validi_non_allocati: "0.0000",
  residui_in_scadenza: "0.0000",
  budget_residuo_progetti_in_corso: "0.0000",
  sforamenti_progetti_in_corso: "0.0000",
  residui_scaduti: "0.0000",
  residui_potenziali_da_verificare: "0.0000",
};

const reconciliation = {
  riepilogo: {
    stato: "ALLINEATO",
    stato_dati: "DISPONIBILI",
    righe: 1,
    righe_confrontabili: 1,
    ok: 1,
    ko: 0,
    assenti_in_ppm: 0,
    delta_totale: "0.0000",
    percentuale_allineati: "100.00",
    snapshot_estratto_il: "2026-10-20",
  },
};

describe("DashboardPage", () => {
  beforeEach(() => {
    getMock.mockImplementation((path) => {
      if (path === "/dashboard") {
        return Promise.resolve({
          generato_il: "2026-10-23",
          progetti_per_stato: [
            { stato: "ATTIVO", conteggio: 2 },
            { stato: "CHIUSO", conteggio: 1 },
          ],
          wallet: { anno: 2026, allocato: "10.0000", consumato: "4.0000", disponibile: "6.0000" },
          prossime_fatturazioni: {
            count: 1,
            limit: 50,
            results: [
              {
                id: "milestone-1",
                progetto_id: "project-1",
                progetto_codice: "PRJ-01",
                data_pianificata: "2026-10-10",
                data_fatturazione: "2026-10-31",
                data_effettiva: null,
                classificazione: "MESE_CORRENTE",
                stato: "PIANIFICATA",
                numero_spostamenti: 0,
                spostamenti: [],
              },
            ],
          },
        });
      }
      if (path.includes("/wallet/")) return Promise.resolve(wallet);
      return Promise.resolve(reconciliation);
    });
  });

  afterEach(() => vi.clearAllMocks());

  it("mostra grafici API e fatturazioni del mese con data prevista e data di fine mese", async () => {
    renderPage();

    expect(await screen.findByText("Distribuzione progetti per stato")).toBeInTheDocument();
    expect(screen.getByText("Prossime fatturazioni")).toBeInTheDocument();
    expect(screen.getByText("PRJ-01")).toBeInTheDocument();
    expect(screen.queryByText("Scaduta")).not.toBeInTheDocument();
    expect(screen.getByText("10/10/2026")).toBeInTheDocument();
    expect(screen.getByText("31/10/2026")).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith("/dashboard");
  });

  it("rende esplicito il dataset vuoto", async () => {
    getMock.mockImplementation((path) => {
      if (path === "/dashboard") {
        return Promise.resolve({
          generato_il: "2026-10-23",
          progetti_per_stato: [],
          wallet: { anno: 2026, allocato: "0.0000", consumato: "0.0000", disponibile: "0.0000" },
          prossime_fatturazioni: { count: 0, limit: 50, results: [] },
        });
      }
      if (path.includes("/wallet/")) return Promise.resolve(wallet);
      return Promise.resolve(reconciliation);
    });

    renderPage();

    expect(
      await screen.findByText("Nessuna milestone aperta prevista nel mese corrente."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Nessun dato disponibile per il grafico.")).toHaveLength(2);
  });
});
