import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ImportazionePage } from "@/features/importazione/ImportazionePage";
import { api } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    API_BASE: "/api/v1",
    api: {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
    },
  };
});

const getMock = vi.mocked(api.get);
const postMock = vi.mocked(api.post);

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  });

  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ImportazionePage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("ImportazionePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getMock.mockImplementation((url: string) => {
      if (url === "/imports/operational") {
        return Promise.resolve({
          importazioni: [
            {
              id: "batch-1",
              file: "Andamento_2026_w44.xlsx",
              stato: "APPLIED",
              stato_etichetta: "Applicato",
              impronta: "hash123",
              creato_il: "2026-11-05T10:00:00Z",
              operatore: "Mario Rossi",
              applicato_da: "Mario Rossi",
              applicato_il: "2026-11-05T10:05:00Z",
              errore: "",
              confermabile: false,
              report: {
                applicato: {
                  movimenti: 45,
                  giornate: "17.5625",
                  operatore: "Mario Rossi",
                  istante: "2026-11-05T10:05:00Z",
                },
              },
            },
          ],
        });
      }
      return Promise.reject(new Error(`Unhandled GET ${url}`));
    });
  });

  it("renderizza correttamente l'intestazione, lo stepper e la dropzone di caricamento", () => {
    renderPage();

    expect(screen.getByText("Importazione Estratto Operativo")).toBeInTheDocument();
    expect(screen.getByText("Consuntivi Settimanali")).toBeInTheDocument();

    // Stepper
    expect(screen.getByText("1. Caricamento")).toBeInTheDocument();
    expect(screen.getByText("2. Analisi & Controlli")).toBeInTheDocument();
    expect(screen.getByText("3. Riconciliazione")).toBeInTheDocument();
    expect(screen.getByText("4. Anteprima Dettaglio")).toBeInTheDocument();
    expect(screen.getByText("5. Ledger Finale")).toBeInTheDocument();

    // Dropzone
    expect(
      screen.getByText("Trascina qui l'estratto Excel oppure clicca per selezionarlo"),
    ).toBeInTheDocument();

    // Storico
    expect(screen.getByText("Storico delle Importazioni")).toBeInTheDocument();
  });

  it("consente di selezionare un file e avviare l'analisi mostrando KPI e anteprima", async () => {
    const mockBatch = {
      id: "batch-test-1",
      file: "Andamento_2026_w45.xlsx",
      stato: "PREVIEW",
      stato_etichetta: "Bozza",
      impronta: "abc987",
      creato_il: "2026-11-12T09:00:00Z",
      operatore: "Luigi Verdi",
      applicato_da: null,
      applicato_il: null,
      errore: "",
      confermabile: true,
      report: {
        totale_righe: 25,
        totale_giornate: "12.5000",
        sezioni: [
          {
            sezione: "PROGETTI",
            etichetta: "Progetti",
            righe_lette: 15,
            righe_importabili: 15,
            righe_da_associare: 0,
            righe_in_errore: 0,
            righe_di_totale_escluse: 0,
            giornate: "7.5000",
          },
          {
            sezione: "WALLET",
            etichetta: "Wallet",
            righe_lette: 5,
            righe_importabili: 5,
            righe_da_associare: 0,
            righe_in_errore: 0,
            righe_di_totale_escluse: 1,
            giornate: "2.5000",
          },
          {
            sezione: "ORGANICO",
            etichetta: "Organico allargato",
            righe_lette: 5,
            righe_importabili: 5,
            righe_da_associare: 0,
            righe_in_errore: 0,
            righe_di_totale_escluse: 1,
            giornate: "2.5000",
          },
        ],
        problemi: [],
        da_associare: [],
      },
      righe: [
        {
          id: "riga-1",
          sezione: "PROGETTI",
          foglio: "Progetti",
          riga_excel: 2,
          destinazione_excel: "PRJ-ALPHA",
          destinazione_risolta: "Progetto Alpha",
          collaboratore_excel: "Rossi Mario",
          utente: "Mario Rossi",
          data: "2026-11-03",
          giornate: "1.0000",
          descrizione: "Sviluppo backend",
          stato: "PRONTA",
          motivazione: "",
          consuntivo: null,
        },
      ],
    };

    postMock.mockResolvedValueOnce(mockBatch);

    const user = userEvent.setup();
    renderPage();

    // Seleziona file
    const file = new File(["test"], "Andamento_2026_w45.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(fileInput).not.toBeNull();

    await user.upload(fileInput, file);

    expect(screen.getByText("Andamento_2026_w45.xlsx")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analizza estratto" })).toBeInTheDocument();

    // Clicca analizza
    await user.click(screen.getByRole("button", { name: "Analizza estratto" }));

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith("/imports/operational/preview", expect.any(FormData));
    });

    // KPI cards renderizzate
    expect(await screen.findByText("Righe Dati Rilevate")).toBeInTheDocument();
    expect(screen.getByText("Volume Giornate")).toBeInTheDocument();
    expect(screen.getByText("Conforme")).toBeInTheDocument();

    // Schede Sezioni
    expect(screen.getByText("Console Controlli & Integrità")).toBeInTheDocument();
    expect(screen.getByText("Nessuna anomalia riscontrata")).toBeInTheDocument();

    // Dettaglio righe
    expect(screen.getByText("Progetto Alpha")).toBeInTheDocument();
    expect(screen.getByText("Sviluppo backend")).toBeInTheDocument();
  });

  it("mostra le voci da associare quando presenti e permette di salvarle", async () => {
    const mockBatchWithMappings = {
      id: "batch-test-2",
      file: "Andamento_con_errori.xlsx",
      stato: "PREVIEW",
      stato_etichetta: "Bozza",
      impronta: "xyz123",
      creato_il: "2026-11-12T11:00:00Z",
      operatore: "Admin",
      applicato_da: null,
      applicato_il: null,
      errore: "",
      confermabile: false,
      report: {
        totale_righe: 10,
        totale_giornate: "5.0000",
        sezioni: [
          {
            sezione: "PROGETTI",
            etichetta: "Progetti",
            righe_lette: 10,
            righe_importabili: 8,
            righe_da_associare: 2,
            righe_in_errore: 0,
            righe_di_totale_escluse: 0,
            giornate: "5.0000",
          },
        ],
        problemi: [
          {
            livello: "WARNING",
            foglio: "Progetti",
            cella: "A4",
            riga: 4,
            messaggio: "Codice progetto sconosciuto PRJ-UNKNOWN",
          },
        ],
        da_associare: [
          {
            chiave: "PROGETTO:PRJ-UNKNOWN",
            tipo: "PROGETTO",
            tipo_etichetta: "Progetto",
            sezione: "PROGETTI",
            valore: "PRJ-UNKNOWN",
            anno: 2026,
            semestre: "",
            righe: ["2", "4"],
            suggerito: "prj-alpha-id",
            candidati: [
              {
                id: "prj-alpha-id",
                etichetta: "Progetto Alpha",
                dettaglio: "IM26001",
                somiglianza: 85,
              },
            ],
          },
        ],
      },
      righe: [],
    };

    postMock.mockResolvedValueOnce(mockBatchWithMappings);

    const user = userEvent.setup();
    renderPage();

    const file = new File(["test"], "Andamento_con_errori.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, file);
    await user.click(screen.getByRole("button", { name: "Analizza estratto" }));

    // Sezione Riconciliazione visibile
    expect(await screen.findByText("3. Riconciliazione Voci Excel Mancanti")).toBeInTheDocument();
    expect(screen.getByText("PRJ-UNKNOWN")).toBeInTheDocument();
    expect(screen.getByText('Suggerito: "Progetto Alpha" (preselezionato)')).toBeInTheDocument();

    // Se l'utente resetta la scelta, appare il pulsante rapido per riapplicare il suggerimento
    const select = screen.getByRole("combobox", {
      name: "Destinazione per PRJ-UNKNOWN",
    });
    await user.selectOptions(select, "");
    expect(screen.getByText('Usa "Progetto Alpha"')).toBeInTheDocument();

    // Console problemi
    expect(screen.getByText("0 errori · 1 avviso")).toBeInTheDocument();
    expect(screen.getByText("Codice progetto sconosciuto PRJ-UNKNOWN")).toBeInTheDocument();
  });

  it("permette di confermare l'importazione quando confermabile e mostra la ricevuta di esito", async () => {
    const mockReadyBatch = {
      id: "batch-ready-1",
      file: "Andamento_pronto.xlsx",
      stato: "PREVIEW",
      stato_etichetta: "Bozza",
      impronta: "impronta-ok-123",
      creato_il: "2026-11-12T10:00:00Z",
      operatore: "Admin",
      applicato_da: null,
      applicato_il: null,
      errore: "",
      confermabile: true,
      report: {
        totale_righe: 5,
        totale_giornate: "2.0000",
        sezioni: [
          {
            sezione: "PROGETTI",
            etichetta: "Progetti",
            righe_lette: 5,
            righe_importabili: 5,
            righe_da_associare: 0,
            righe_in_errore: 0,
            righe_di_totale_escluse: 0,
            giornate: "2.0000",
          },
        ],
        problemi: [],
        da_associare: [],
      },
      righe: [],
    };

    const mockAppliedBatch = {
      ...mockReadyBatch,
      stato: "APPLIED",
      stato_etichetta: "Applicato",
      confermabile: false,
      report: {
        ...mockReadyBatch.report,
        applicato: {
          movimenti: 5,
          giornate: "2.0000",
          operatore: "Admin",
          istante: "2026-11-12T10:02:00Z",
        },
      },
    };

    postMock.mockResolvedValueOnce(mockReadyBatch);
    postMock.mockResolvedValueOnce(mockAppliedBatch);

    const user = userEvent.setup();
    renderPage();

    const file = new File(["test"], "Andamento_pronto.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, file);
    await user.click(screen.getByRole("button", { name: "Analizza estratto" }));

    // Clicca conferma
    const confirmBtn = await screen.findByRole("button", {
      name: "Conferma e applica importazione",
    });
    expect(confirmBtn).not.toBeDisabled();

    await user.click(confirmBtn);

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith("/imports/operational/batch-ready-1/apply", {
        impronta: "impronta-ok-123",
      });
    });

    // Ricevuta di successo
    expect(await screen.findByText("Importazione applicata con successo!")).toBeInTheDocument();
    expect(screen.getByText("ID Batch: batch-ready-1")).toBeInTheDocument();
  });
});
