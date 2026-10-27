import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as sessionModule from "@/features/auth/session";
import type { Session } from "@/features/auth/session";
import { EditProjectDialog } from "@/features/projects/EditProjectDialog";
import { ProjectsPage } from "@/features/projects/ProjectsPage";
import { api } from "@/lib/api";
import type { ProblemDetail } from "@/lib/api";
import "@/i18n";

vi.mock("@/lib/api", () => {
  class MockApiError extends Error {
    problem: ProblemDetail;
    status: number;
    constructor(problem: ProblemDetail) {
      super(problem.detail || problem.title);
      this.problem = problem;
      this.status = problem.status;
    }
    get code(): string {
      return this.problem.code;
    }
    get fieldErrors(): Record<string, string> {
      const result: Record<string, string> = {};
      for (const item of this.problem.errors ?? []) {
        result[item.campo] = item.messaggio;
      }
      return result;
    }
  }

  return {
    api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
    ApiError: MockApiError,
  };
});

const getMock = vi.mocked(api.get);
const postMock = vi.mocked(api.post);
const patchMock = vi.mocked(api.patch);
const deleteMock = vi.mocked(api.delete);

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

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ProjectsPage ed EditProjectDialog — Tranche 4", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("mostra il pulsante EDIT arancione per Admin su ogni progetto", async () => {
    mockSession({
      roles: ["admin"],
      is_admin: true,
      can_write: true,
      capabilities: ["projects.edit"],
    });

    getMock.mockImplementation((path: string) => {
      if (path === "/projects/balances") {
        return Promise.resolve({
          count: 1,
          results: [
            {
              id: "proj-123",
              codice: "IM26001-DEMO",
              titolo: "Progetto Test",
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
            },
          ],
        });
      }
      return Promise.reject(new Error("Unknown path"));
    });

    renderWithProviders(<ProjectsPage />);

    const editButton = await screen.findByTestId("edit-project-proj-123");
    expect(editButton).toBeInTheDocument();
    expect(editButton).toHaveClass("bg-amber-500");
    expect(screen.getByRole("columnheader", { name: "Titolo" })).toHaveClass("min-w-64");
    expect(screen.getByText("Progetto Test").closest("td")).toHaveClass(
      "min-w-64",
      "whitespace-normal",
    );
    expect(screen.getByRole("columnheader", { name: "Budget" })).toHaveClass("text-right");
    expect(screen.getByTitle("Budget API: 10.0000 gg").closest("td")).toHaveClass(
      "text-right",
      "tabular-nums",
    );
  });

  it("mostra EDIT solo sul progetto proprio per il referente BMED", async () => {
    mockSession({
      roles: ["referente_bmed"],
      capabilities: ["projects.annotate_own"],
    });

    getMock.mockImplementation((path: string) => {
      if (path === "/projects/balances") {
        return Promise.resolve({
          count: 2,
          results: [
            {
              id: "proj-own",
              codice: "IM26001-OWN",
              titolo: "Mio Progetto",
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
              permissions: { edit: false, annotate: true },
            },
            {
              id: "proj-other",
              codice: "IM26002-OTHER",
              titolo: "Altro Progetto",
              tipo_contratto: "AQL",
              budget: "5.0000",
              consuntivi_diretti: "0.0000",
              allocato_a_wallet: "0.0000",
              consumato_via_wallet: "0.0000",
              consumato_totale: "0.0000",
              residuo: "5.0000",
              stato_consuntivazione: "ATTIVO",
              stato_fatturazione: "DA_FATTURARE",
              stato_offerta: "ACCETTATA",
              stato_residuo: "VALIDO",
              residuo_scade_il: null,
              residuo_giorni_alla_scadenza: null,
              residuo_motivo: "Ok",
              spiegazione_residuo: "Ok",
              permissions: { edit: false, annotate: false },
            },
          ],
        });
      }
      return Promise.reject(new Error("Unknown path"));
    });

    renderWithProviders(<ProjectsPage />);

    expect(await screen.findByTestId("edit-project-proj-own")).toBeInTheDocument();
    expect(screen.queryByTestId("edit-project-proj-other")).not.toBeInTheDocument();
  });

  it("consente al fornitore di validare una chiusura proposta senza mostrare EDIT", async () => {
    mockSession({
      roles: ["fornitore"],
      capabilities: ["projects.create", "projects.validate_closure", "imports.upload"],
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    postMock.mockResolvedValue({ stato_operativo: "CHIUSO" });

    getMock.mockImplementation((path: string) => {
      if (path === "/projects/balances") {
        return Promise.resolve({
          count: 1,
          results: [
            {
              id: "proj-fornitore",
              version: 4,
              codice: "IM26001-SUPPLIER",
              titolo: "Progetto Fornitore",
              tipo_contratto: "AQL",
              budget: "10.0000",
              consuntivi_diretti: "0.0000",
              allocato_a_wallet: "0.0000",
              consumato_via_wallet: "0.0000",
              consumato_totale: "0.0000",
              residuo: "10.0000",
              stato_consuntivazione: "ATTIVO",
              stato_operativo: "CHIUSURA_DA_VALIDARE",
              stato_fatturazione: "DA_FATTURARE",
              stato_offerta: "ACCETTATA",
              stato_residuo: "VALIDO",
              residuo_scade_il: null,
              residuo_giorni_alla_scadenza: null,
              residuo_motivo: "Ok",
              spiegazione_residuo: "Ok",
              permissions: { edit: false, annotate: false, validate_closure: true },
            },
          ],
        });
      }
      return Promise.reject(new Error("Unknown path"));
    });

    renderWithProviders(<ProjectsPage />);

    await screen.findByRole("heading", { name: "Progetti" });
    expect(screen.queryByTestId("edit-project-proj-fornitore")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("validate-closure-proj-fornitore"));
    expect(postMock).toHaveBeenCalledWith("/projects/proj-fornitore/validate-closure", {
      expected_version: 4,
    });
  });

  it("gestisce apertura form, precompilazione, codice readonly e invio PATCH con version", async () => {
    mockSession({
      roles: ["admin"],
      is_admin: true,
      capabilities: ["projects.edit"],
    });

    getMock.mockImplementation((path: string) => {
      if (path === "/projects/options") {
        return Promise.resolve({
          contract_types: [{ value: "AQL", label: "AQL" }],
          offer_statuses: [{ value: "ACCETTATA", label: "Accettata" }],
          timesheet_statuses: [{ value: "ATTIVO", label: "Attivo" }],
          billing_statuses: [{ value: "DA_FATTURARE", label: "Da fatturare" }],
          reliabilities: [{ value: "CERTO", label: "Certo" }],
          organizations: [],
          people: [],
        });
      }
      if (path === "/projects/proj-123") {
        return Promise.resolve({
          id: "proj-123",
          code: "IM26001-CODE",
          title: "Progetto Alfa",
          contract_type: "AQL",
          aro_code: "ARO-1",
          rda_code: "RDA-1",
          deliverable: "Delivery",
          client_owner: null,
          supplier_owner: null,
          budget_days: "20.0000",
          start_date: "2026-01-01",
          planned_end_date: "2026-06-30",
          actual_closure_date: null,
          offer_status: "ACCETTATA",
          timesheet_status: "ATTIVO",
          billing_status: "DA_FATTURARE",
          notes: "Nota iniziale",
          reliability: "CERTO",
          verification_points: [],
          version: 3,
          permissions: {
            edit: true,
            delete: true,
            annotate: true,
            editable_fields: ["title", "notes"],
          },
          readonly: {
            code: "Il codice è bloccato perché può essere referenziato da import e ledger.",
          },
        });
      }
      return Promise.reject(new Error("Unknown path"));
    });

    patchMock.mockResolvedValue({
      id: "proj-123",
      version: 4,
    });

    const user = userEvent.setup();
    renderWithProviders(
      <EditProjectDialog projectId="proj-123" open={true} onOpenChange={vi.fn()} />,
    );

    // Aspetta caricamento
    expect(await screen.findByDisplayValue("Progetto Alfa")).toBeInTheDocument();
    expect(screen.getByText("IM26001-CODE")).toBeInTheDocument();
    expect(
      screen.getByText(/Il codice è bloccato perché può essere referenziato da import e ledger/),
    ).toBeInTheDocument();
    expect(screen.getByText("v3")).toBeInTheDocument();

    // Modifica titolo e salva
    const titleInput = screen.getByDisplayValue("Progetto Alfa");
    await user.clear(titleInput);
    await user.type(titleInput, "Progetto Alfa Aggiornato");

    const saveButton = screen.getByRole("button", { name: "Salva Modifiche" });
    await user.click(saveButton);

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith(
        "/projects/proj-123",
        expect.objectContaining({
          expected_version: 3,
          title: "Progetto Alfa Aggiornato",
        }),
      );
    });
  });

  it("richiede il codice progetto prima della cancellazione", async () => {
    deleteMock.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderWithProviders(
      <EditProjectDialog projectId="proj-123" open={true} onOpenChange={vi.fn()} />,
    );
    expect(await screen.findByDisplayValue("Progetto Alfa")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Elimina progetto" }));
    const confirm = screen.getByRole("button", { name: "Elimina definitivamente" });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText("Codice progetto"), "IM26001-CODE");
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    await waitFor(() =>
      expect(deleteMock).toHaveBeenCalledWith("/projects/proj-123", expect.anything()),
    );
  });
});
