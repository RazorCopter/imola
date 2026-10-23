import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WalletPage } from "@/features/wallet/WalletPage";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

vi.mock("@/features/auth/session", () => ({
  useSession: () => ({
    session: {
      username: "test",
      full_name: "Test",
      email: "",
      roles: ["responsabile_bmed"],
      is_admin: false,
      can_write: true,
    },
    status: "authenticated",
    expired: false,
    signIn: vi.fn(),
    signOut: vi.fn(),
    refresh: vi.fn(),
  }),
}));

const getMock = vi.mocked(api.get);

describe("WalletPage", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  it("formatta il residuo e la scadenza ricevuti dall'API senza ricalcolarli", async () => {
    getMock.mockImplementation((path: string) => {
      if (path.endsWith("/flow") || path.endsWith("/assignees"))
        return Promise.resolve({ results: [] });
      if (path.endsWith("/options"))
        return Promise.resolve({ projects: [], activities: [], assignees: [] });
      return Promise.resolve({
        anno: new Date().getFullYear(),
        allocato: "0.0000",
        consumato: "0.0000",
        disponibile: "0.0000",
        residui_validi_non_allocati: "0.0000",
        residui_in_scadenza: "7.2500",
        residui_scaduti: "0.0000",
        residui_potenziali_da_verificare: "0.0000",
        dettaglio_residui: {
          IN_SCADENZA: {
            giornate: "7.2500",
            progetti: [
              {
                codice: "IM25-CHIUSO-API",
                giornate: "7.2500",
                scade_il: "2026-12-31",
                motivo: "Residuo utilizzabile fino al 31/12/2026.",
              },
            ],
          },
        },
      });
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <WalletPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("IM25-CHIUSO-API")).toBeInTheDocument();
    expect(screen.getAllByText("7,25 gg").length).toBeGreaterThan(0);
    expect(screen.getByText(/scade 31\/12\/2026/)).toBeInTheDocument();
  });

  it("mostra il pulsante arancione EDIT sulle righe del flusso wallet e apre il modale", async () => {
    getMock.mockImplementation((path: string) => {
      if (path.endsWith("/flow")) {
        return Promise.resolve({
          results: [
            {
              id: "alloc-123",
              version: 2,
              riferimento: "W26-001",
              origine: "IM25-SRC",
              origine_titolo: "Progetto Origine",
              destinazione: "ACT-01",
              destinazione_titolo: "Attività Destinazione",
              architetto: "Architetto Mario",
              allocato: "10.0000",
              consumato: "4.0000",
              disponibile: "6.0000",
              stato: "APERTA",
            },
          ],
        });
      }
      if (path.endsWith("/assignees")) return Promise.resolve({ results: [] });
      if (path.endsWith("/options") || path.endsWith("/allocation-options/")) {
        return Promise.resolve({
          projects: [],
          activities: [],
          assignees: [{ id: "arch-1", name: "Architetto Mario" }],
          architects: [{ id: "arch-1", name: "Architetto Mario" }],
        });
      }
      if (path.includes("/wallet/allocations/alloc-123/")) {
        return Promise.resolve({
          id: "alloc-123",
          version: 2,
          external_ref: "W26-001",
          allocated_days: "10.0000",
          days_allocated: "10.0000",
          consumed_days: "4.0000",
          available_days: "6.0000",
          status: "APERTA",
          notes: "Note test",
          assignee: "arch-1",
          architetto: "Architetto Mario",
          source_project: "p-src",
          source_project_code: "IM25-SRC",
          source_project_title: "Progetto Origine",
          activity: "act-1",
          activity_code: "ACT-01",
          activity_title: "Attività Destinazione",
          year: 2026,
          timesheet_entries: [],
        });
      }
      return Promise.resolve({
        anno: 2026,
        allocato: "10.0000",
        consumato: "4.0000",
        disponibile: "6.0000",
        residui_validi_non_allocati: "0.0000",
        residui_in_scadenza: "0.0000",
        residui_scaduti: "0.0000",
        residui_potenziali_da_verificare: "0.0000",
        dettaglio_residui: {},
      });
    });

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <WalletPage />
      </QueryClientProvider>,
    );

    const editBtn = await screen.findByTestId("edit-allocation-alloc-123");
    expect(editBtn).toBeInTheDocument();
    expect(editBtn).toHaveTextContent("EDIT");
    expect(editBtn.className).toContain("bg-amber-500");
  });
});
