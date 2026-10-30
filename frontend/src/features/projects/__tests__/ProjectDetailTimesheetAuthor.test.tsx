import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as sessionModule from "@/features/auth/session";
import type { Session } from "@/features/auth/session";
import { ProjectDetailPage } from "@/features/projects/ProjectDetailPage";
import { api } from "@/lib/api";
import "@/i18n";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  ApiError: class extends Error {},
}));

const getMock = vi.mocked(api.get);
const postMock = vi.mocked(api.post);

function mockSession(session: Partial<Session>) {
  vi.spyOn(sessionModule, "useSession").mockReturnValue({
    session: {
      username: "admin",
      full_name: "Admin",
      email: "admin@example.test",
      roles: [],
      is_admin: false,
      can_write: false,
      ...session,
    },
    status: "authenticated",
    expired: false,
    signIn: vi.fn(),
    signOut: vi.fn(),
    refresh: vi.fn(),
  });
}

const BALANCE = {
  id: "proj-1",
  codice: "IM26001",
  titolo: "Progetto",
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
  residuo_motivo: "Ok",
  spiegazione_residuo: "Ok",
  permissions: { edit: true, annotate: true },
};

function mockEndpoints() {
  getMock.mockImplementation((path: string) => {
    if (path === "/projects/balances") return Promise.resolve({ count: 1, results: [BALANCE] });
    if (path === "/projects/proj-1")
      return Promise.resolve({
        ...BALANCE,
        billing_status: "DA_FATTURARE",
        billing_milestones: [],
        notes: "",
        client_owner_name: null,
        supplier_owner_name: null,
      });
    if (path === "/projects/proj-1/ledger") return Promise.resolve({ consuntivi: [], wallet: [] });
    if (path === "/audit/project/proj-1") return Promise.resolve({ results: [] });
    if (path === "/timesheets/authors")
      return Promise.resolve({
        results: [{ id: 7, username: "imola", full_name: "Mario Rossi", roles: ["fornitore"] }],
      });
    return Promise.reject(new Error(`Unknown path ${path}`));
  });
}

function renderPage(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/progetti/proj-1"]}>
        <Routes>
          <Route path="/progetti/:projectId" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ProjectDetailPage — autore del consuntivo", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockEndpoints();
  });

  it("l'Admin sceglie l'utente che consuntiva e lo invia nel payload", async () => {
    mockSession({
      roles: ["admin"],
      is_admin: true,
      can_write: true,
      capabilities: ["timesheets.create", "timesheets.assign_author"],
    });
    postMock.mockResolvedValue({ id: "entry-1" });

    renderPage(<ProjectDetailPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Consuntivi" }));
    await userEvent.click(await screen.findByRole("button", { name: "Consuntiva" }));

    const select = await screen.findByLabelText("Utente che consuntiva");
    await waitFor(() => expect(screen.getByRole("option", { name: /Mario Rossi/ })).toBeTruthy());
    await userEvent.selectOptions(select, "7");
    await userEvent.type(screen.getByLabelText("Giornate"), "2");
    await userEvent.type(screen.getByLabelText("Descrizione"), "Analisi");
    await userEvent.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith(
        "/projects/proj-1/ledger",
        expect.objectContaining({ giornate: "2", descrizione: "Analisi", utente: "7" }),
      ),
    );
  });

  it("al Fornitore il campo non compare e il payload resta senza utente", async () => {
    mockSession({
      roles: ["fornitore"],
      capabilities: ["timesheets.create"],
    });
    postMock.mockResolvedValue({ id: "entry-2" });

    renderPage(<ProjectDetailPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Consuntivi" }));
    await userEvent.click(await screen.findByRole("button", { name: "Consuntiva" }));

    expect(screen.queryByLabelText("Utente che consuntiva")).toBeNull();
    expect(getMock).not.toHaveBeenCalledWith("/timesheets/authors");

    await userEvent.type(screen.getByLabelText("Giornate"), "1");
    await userEvent.type(screen.getByLabelText("Descrizione"), "Analisi");
    await userEvent.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][1]).not.toHaveProperty("utente");
  });
});
