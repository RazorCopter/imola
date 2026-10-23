import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/AppShell";
import { AnomaliesPage } from "@/features/anomalies/AnomaliesPage";
import * as sessionModule from "@/features/auth/session";
import type { Session } from "@/features/auth/session";
import { ProjectDetailPage } from "@/features/projects/ProjectDetailPage";
import { ProjectsPage } from "@/features/projects/ProjectsPage";
import { ReviewQueuePage } from "@/features/review/ReviewQueuePage";
import { WalletPage } from "@/features/wallet/WalletPage";
import "@/i18n";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

const getMock = vi.mocked(api.get);

function mockSession(session: Partial<Session> | null) {
  const fullSession: Session | null = session
    ? {
        username: "test-user",
        full_name: "Test User",
        email: "test@example.test",
        roles: [],
        is_admin: false,
        can_write: false,
        ...session,
      }
    : null;

  vi.spyOn(sessionModule, "useSession").mockReturnValue({
    session: fullSession,
    status: fullSession ? "authenticated" : "anonymous",
    expired: false,
    signIn: vi.fn(),
    signOut: vi.fn(),
    refresh: vi.fn(),
  });
}

function renderWithProviders(ui: ReactElement, initialPath = "/") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("coerenza visibilità e navigazione per ruolo", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    getMock.mockReset();
  });

  it("mostra tutte le voci di menu consultive e non espone amministrazione come link ingannevole", () => {
    mockSession({ roles: ["fornitore"], can_write: false });

    renderWithProviders(<AppShell onOpenCommandPalette={vi.fn()} />);

    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Progetti" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Wallet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Organico Allargato" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Riconciliazione PPM" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Anomalie" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Coda di revisione" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Amministrazione/i })).not.toBeInTheDocument();
  });

  it("consente a Admin e Responsabile di vedere il pulsante 'Nuovo progetto'", async () => {
    mockSession({ roles: ["responsabile_bmed"], can_write: true });
    getMock.mockResolvedValue({ results: [], count: 0 });

    renderWithProviders(<ProjectsPage />);

    expect(await screen.findByRole("button", { name: "Nuovo progetto" })).toBeInTheDocument();
  });

  it("nasconde il pulsante 'Nuovo progetto' a Fornitore e Referente", async () => {
    mockSession({ roles: ["fornitore"], can_write: false });
    getMock.mockResolvedValue({ results: [], count: 0 });

    renderWithProviders(<ProjectsPage />);

    await screen.findByRole("heading", { name: "Progetti" });
    expect(screen.queryByRole("button", { name: "Nuovo progetto" })).not.toBeInTheDocument();
  });

  it("mostra l'azione di aggiornamento data fine solo sui progetti con annotazione consentita", async () => {
    mockSession({ roles: ["referente_bmed"], can_write: false });
    getMock.mockImplementation((path: string) => {
      if (path.startsWith("/audit/project/")) return Promise.resolve({ results: [] });
      return Promise.resolve({
        results: [
          {
            id: "proj-1",
            codice: "IM-OWN",
            titolo: "Progetto proprio",
            tipo_contratto: "AQL",
            budget: "10.0000",
            consuntivi_diretti: "0.0000",
            allocato_a_wallet: "0.0000",
            consumato_via_wallet: "0.0000",
            consumato_totale: "0.0000",
            residuo: "10.0000",
            stato_consuntivazione: "ATTIVO",
            stato_fatturazione: "DA_FATTURARE",
            stato_offerta: "ACCETTATA",
            stato_residuo: "VALIDO",
            residuo_scade_il: null,
            residuo_giorni_alla_scadenza: null,
            residuo_motivo: "Valido",
            spiegazione_residuo: "Ok",
            permissions: { annotate: true },
          },
        ],
      });
    });

    renderWithProviders(
      <Routes>
        <Route path="/progetti/:projectId" element={<ProjectDetailPage />} />
      </Routes>,
      "/progetti/proj-1",
    );

    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "IM-OWN" });
    const trigger = screen.getByRole("tab", { name: "Anomalie" });
    await user.click(trigger);
    expect(
      await screen.findByRole("button", { name: "Aggiorna data fine prevista" }),
    ).toBeInTheDocument();
  });

  it("mostra nota di sola consultazione sul progetto altrui o per ruoli non abilitati", async () => {
    mockSession({ roles: ["fornitore"], can_write: false });
    getMock.mockImplementation((path: string) => {
      if (path.startsWith("/audit/project/")) return Promise.resolve({ results: [] });
      return Promise.resolve({
        results: [
          {
            id: "proj-2",
            codice: "IM-OTHER",
            titolo: "Progetto altrui",
            tipo_contratto: "AQL",
            budget: "10.0000",
            consuntivi_diretti: "0.0000",
            allocato_a_wallet: "0.0000",
            consumato_via_wallet: "0.0000",
            consumato_totale: "0.0000",
            residuo: "10.0000",
            stato_consuntivazione: "ATTIVO",
            stato_fatturazione: "DA_FATTURARE",
            stato_offerta: "ACCETTATA",
            stato_residuo: "VALIDO",
            residuo_scade_il: null,
            residuo_giorni_alla_scadenza: null,
            residuo_motivo: "Valido",
            spiegazione_residuo: "Ok",
            permissions: { annotate: false },
          },
        ],
      });
    });

    renderWithProviders(
      <Routes>
        <Route path="/progetti/:projectId" element={<ProjectDetailPage />} />
      </Routes>,
      "/progetti/proj-2",
    );

    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "IM-OTHER" });
    const trigger = screen.getByRole("tab", { name: "Anomalie" });
    await user.click(trigger);
    expect(
      await screen.findByText(
        "Consultazione disponibile; le modifiche non sono consentite per questo progetto.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Aggiorna data fine prevista" }),
    ).not.toBeInTheDocument();
  });

  it("nasconde mutation wallet a ruoli consultivi", async () => {
    mockSession({ roles: ["referente_bmed"], can_write: false });
    getMock.mockImplementation((path: string) => {
      if (path.endsWith("/flow")) {
        return Promise.resolve({
          results: [
            {
              id: "flow-1",
              riferimento: "W-1",
              origine: "IM-ORIG",
              origine_titolo: "Origine",
              destinazione: "IM-DEST",
              destinazione_titolo: "Destinazione",
              allocato: "5.0000",
              consumato: "2.0000",
              disponibile: "3.0000",
              stato: "ATTIVA",
            },
          ],
        });
      }
      return Promise.resolve({
        anno: 2026,
        allocato: "5.0000",
        consumato: "2.0000",
        disponibile: "3.0000",
        residui_validi_non_allocati: "0.0000",
        residui_in_scadenza: "0.0000",
        residui_scaduti: "0.0000",
        residui_potenziali_da_verificare: "0.0000",
        dettaglio_residui: {},
      });
    });

    renderWithProviders(<WalletPage />);

    await screen.findByText("Wallet 2026");
    expect(screen.queryByRole("button", { name: "Riduci al consumato" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Chiudi" })).not.toBeInTheDocument();
  });

  it("nasconde esecuzione controlli anomalie a ruoli consultivi", async () => {
    mockSession({ roles: ["fornitore"], can_write: false });
    getMock.mockResolvedValue({ results: [] });

    renderWithProviders(<AnomaliesPage />);

    await screen.findByRole("heading", { name: "Inbox anomalie" });
    expect(screen.queryByRole("button", { name: "Esegui controlli" })).not.toBeInTheDocument();
  });

  it("mostra indicatore di sola lettura nella coda revisione per ruoli non writer", async () => {
    mockSession({ roles: ["referente_bmed"], can_write: false });
    getMock.mockResolvedValue({
      count: 1,
      results: [
        {
          id: "rev-1",
          codice: "IM-REV",
          titolo: "Progetto revisione",
          stato_consuntivazione: "CHIUSO",
          data_chiusura: null,
          data_fine_prevista: "2026-06-30",
          motivo_revisione: "Data chiusura assente",
        },
      ],
    });

    renderWithProviders(<ReviewQueuePage />);

    expect(await screen.findByText("Sola lettura")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Conferma revisione" })).not.toBeInTheDocument();
  });
});
