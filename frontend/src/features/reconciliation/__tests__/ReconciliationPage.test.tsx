import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReconciliationPage } from "@/features/reconciliation/ReconciliationPage";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn() },
}));

const getMock = vi.mocked(api.get);

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ReconciliationPage />
    </QueryClientProvider>,
  );
}

describe("ReconciliationPage", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  it("rende esplicita l'assenza dello snapshot senza KPI verdi o percentuali", async () => {
    getMock.mockResolvedValue({
      riepilogo: {
        stato: "NON_VERIFICABILE",
        stato_dati: "SNAPSHOT_ASSENTE",
        righe: 0,
        righe_confrontabili: 0,
        ok: 0,
        ko: 0,
        assenti_in_ppm: 0,
        delta_totale: null,
        percentuale_allineati: null,
        snapshot_estratto_il: null,
      },
      tolleranza: "0.0100",
      results: [],
    });

    renderPage();

    expect(await screen.findByText("Non verificabile / dati assenti")).toBeInTheDocument();
    expect(screen.getAllByText(/Snapshot PPM assente/).length).toBeGreaterThan(0);
    expect(screen.getByText("Allineate").parentElement?.parentElement).toHaveTextContent(
      "Non disponibile",
    );
    expect(screen.queryByText(/0,00%/)).not.toBeInTheDocument();
    expect(screen.queryByText("Allineato")).not.toBeInTheDocument();
  });

  it("mostra lo stato allineato e la percentuale calcolata dal backend", async () => {
    getMock.mockResolvedValue({
      riepilogo: {
        stato: "ALLINEATO",
        stato_dati: "DISPONIBILI",
        righe: 1,
        righe_confrontabili: 1,
        ok: 1,
        ko: 0,
        assenti_in_ppm: 0,
        delta_totale: "0.0000",
        percentuale_allineati: "100.0000",
        snapshot_estratto_il: "2026-10-16T11:05:00+02:00",
      },
      tolleranza: "0.0100",
      results: [],
    });

    renderPage();

    expect(await screen.findByText("Allineato")).toBeInTheDocument();
    expect(screen.getByText(/1 · 100,0%/)).toBeInTheDocument();
  });
});
