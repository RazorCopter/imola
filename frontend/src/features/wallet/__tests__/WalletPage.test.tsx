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
});
