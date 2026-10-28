import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import userEvent from "@testing-library/user-event";

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
      <MemoryRouter>
        <ReconciliationPage />
      </MemoryRouter>
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

  it("mappa e centra tutti gli esiti backend reali con testo e tono semantici", async () => {
    getMock.mockResolvedValue({
      riepilogo: {
        stato: "NON_ALLINEATO",
        stato_dati: "DISPONIBILI",
        righe: 3,
        righe_confrontabili: 2,
        ok: 1,
        ko: 1,
        assenti_in_ppm: 1,
        delta_totale: "1.0000",
        percentuale_allineati: "50.0000",
        snapshot_estratto_il: "2026-10-16T11:05:00+02:00",
      },
      tolleranza: "0.0100",
      results: [
        {
          codice_progetto: "OK-1",
          nome_progetto: "Allineato",
          progetto_id: "p-ok",
          interno: "1.0000",
          ppm: "1.0000",
          delta: "0.0000",
          esito: "OK",
          snapshot_estratto_il: "2026-10-16T11:05:00+02:00",
          azione_suggerita: "Nessuna azione",
        },
        {
          codice_progetto: "KO-1",
          nome_progetto: "Non allineato",
          progetto_id: "p-ko",
          interno: "2.0000",
          ppm: "1.0000",
          delta: "1.0000",
          esito: "KO",
          snapshot_estratto_il: "2026-10-16T11:05:00+02:00",
          azione_suggerita: "Verificare",
        },
        {
          codice_progetto: "MISS-1",
          nome_progetto: "Assente",
          progetto_id: "p-missing",
          interno: "3.0000",
          ppm: null,
          delta: null,
          esito: "ASSENTE_IN_PPM",
          snapshot_estratto_il: null,
          azione_suggerita: "Associare",
        },
      ],
    });

    renderPage();

    const valid = await screen.findByText("Valido");
    const discrepancy = screen.getByText("DISCREPANZA");
    const missing = screen.getByText("Assente PPM");
    expect(valid).toHaveAttribute("data-outcome", "OK");
    expect(valid).toHaveAttribute("data-tone", "ok");
    expect(discrepancy).toHaveAttribute("data-outcome", "KO");
    expect(discrepancy).toHaveAttribute("data-tone", "danger");
    expect(missing).toHaveAttribute("data-outcome", "ASSENTE_IN_PPM");
    expect(missing).toHaveAttribute("data-tone", "warn");
    expect(valid.closest("td")).toHaveClass("text-center");
    expect(screen.getByRole("columnheader", { name: "Esito" })).toHaveClass("text-center");
    await userEvent.selectOptions(screen.getByLabelText("Filtra esito riconciliazione"), "KO");
    expect(screen.getByText("DISCREPANZA")).toBeInTheDocument();
    expect(screen.queryByText("Valido")).not.toBeInTheDocument();
    expect(screen.getByText("Confronti eseguiti").closest("article")).toHaveTextContent("2");
  });

  it("rende visibile e neutro un esito backend inatteso", async () => {
    getMock.mockResolvedValue({
      riepilogo: {
        stato: "PARZIALE",
        stato_dati: "DISPONIBILI",
        righe: 1,
        righe_confrontabili: 1,
        ok: 0,
        ko: 0,
        assenti_in_ppm: 0,
        delta_totale: null,
        percentuale_allineati: null,
        snapshot_estratto_il: "2026-10-16T11:05:00+02:00",
      },
      tolleranza: "0.0100",
      results: [
        {
          codice_progetto: "FUTURE-1",
          nome_progetto: "Contratto futuro",
          progetto_id: "p-future",
          interno: "1.0000",
          ppm: null,
          delta: null,
          esito: "NON_VERIFICABILE",
          snapshot_estratto_il: null,
          azione_suggerita: "Verificare il contratto",
        },
      ],
    });

    renderPage();

    const fallback = await screen.findByText("Esito sconosciuto: NON_VERIFICABILE");
    expect(fallback).toHaveAttribute("data-tone", "neutral");
    expect(fallback).toHaveAttribute("data-outcome", "NON_VERIFICABILE");
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
      results: [
        {
          codice_progetto: "IM26-CODICE-COMPLETO",
          nome_progetto: "Portale clienti",
          progetto_id: "project-1",
          interno: "4.0000",
          ppm: "4.0000",
          delta: "0.0000",
          esito: "OK",
          snapshot_estratto_il: "2026-10-16T11:05:00+02:00",
          azione_suggerita: "",
        },
        {
          codice_progetto: "IM26-SENZA-NOME",
          nome_progetto: null,
          progetto_id: "project-2",
          interno: "0.0000",
          ppm: "0.0000",
          delta: "0.0000",
          esito: "OK",
          snapshot_estratto_il: "2026-10-16T11:05:00+02:00",
          azione_suggerita: "",
        },
      ],
    });

    renderPage();

    expect(await screen.findByText("Allineato")).toBeInTheDocument();
    expect(screen.getAllByText("Valido")).toHaveLength(2);
    expect(screen.getByText(/1 · 100,0%/)).toBeInTheDocument();
    expect(screen.getByText("IM26-CODICE-COMPLETO")).toBeInTheDocument();
    expect(screen.getByText("Portale clienti")).toBeInTheDocument();
    expect(screen.getByText("Progetto non associato")).toBeInTheDocument();
  });
});
