import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import "@/i18n";
import { CanonePage } from "@/features/canone/CanonePage";
import { api } from "@/lib/api";

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal("ResizeObserver", ResizeObserverMock);

let capabilities: string[] = [];
vi.mock("@/features/auth/session", () => ({
  useSession: () => ({
    session: {
      username: "u",
      full_name: "U",
      email: "",
      roles: [],
      capabilities,
      is_admin: false,
      can_write: false,
    },
  }),
}));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});
const getMock = vi.mocked(api.get);

const list = {
  default_canone_id: "one",
  count: 1,
  results: [
    {
      id: "one",
      version: 1,
      semestre: "2026-S1",
      periodicita: "SEMESTRALE",
      nome: "Canone Organico",
      pianificato: "100.0000",
      riservato: "50.0000",
      disponibile: "50.0000",
      consuntivato: "25.0000",
      residuo: "75.0000",
      stato: "IN_CORSO",
      sottoattivita_count: 1,
    },
  ],
  summary: {
    pianificato: "100.0000",
    riservato: "50.0000",
    disponibile: "50.0000",
    consuntivato: "25.0000",
    residuo: "75.0000",
    sottoattivita: 1,
  },
  filters: {
    semestri: ["2026-S1"],
    stati: ["IN_CORSO"],
    domini: ["EA", "TA", "SA", "CROSS"],
  },
};
const detail = {
  id: "one",
  version: 1,
  name: "Canone Organico",
  semester: "2026-S1",
  periodicity: "SEMESTRALE",
  total_days: "100.0000",
  reserved_days: "50.0000",
  available_days: "50.0000",
  target_base_days: "2.0000",
  target_days_per_week: "4.0000",
  cap_at_total: true,
  start_date: "2026-01-01",
  end_date: "2026-06-30",
  status: {
    consuntivato: "25.0000",
    target_alla_data: "30.0000",
    delta: "5.0000",
    forecast: "75.0000",
    percentuale_forecast: "75.0000",
    proiezione: "In linea con il monte",
    giornate_non_usate_previste: "25.0000",
  },
  subactivities: [
    {
      id: "s1",
      version: 1,
      office: "EA",
      title: "Analisi",
      reserved_days: "50.0000",
      start_date: "2026-01-01",
      end_date: "2026-06-30",
      remaining_reserved_days: "25.0000",
      redmine_ref: "",
      quarter_estimate_days: null,
      forecast_remaining_days: "50.0000",
      notes: "",
      needs_review: false,
      consuntivato: "25.0000",
      timesheet_count: 2,
      consuntivi: [],
    },
    {
      id: "s2",
      version: 1,
      office: "SA",
      title: "Disegno Solution",
      reserved_days: "20.0000",
      start_date: "2026-01-01",
      end_date: "2026-06-30",
      remaining_reserved_days: "20.0000",
      redmine_ref: "",
      quarter_estimate_days: null,
      forecast_remaining_days: "20.0000",
      notes: "",
      needs_review: false,
      consuntivato: "0.0000",
      timesheet_count: 0,
      consuntivi: [],
    },
  ],
};

function renderPage(sessionCapabilities: string[] = []) {
  capabilities = sessionCapabilities;
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <CanonePage />
    </QueryClientProvider>,
  );
}

describe("CanonePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getMock.mockImplementation(
      (url) => Promise.resolve(url.startsWith("/canoni/one") ? detail : list) as never,
    );
  });

  it("correla KPI, grafico, lista e dettaglio ed espone selezione da tastiera", async () => {
    const user = userEvent.setup();
    renderPage();
    expect((await screen.findAllByText("100,00 gg")).length).toBeGreaterThan(0);
    expect(
      screen.getByLabelText("Confronto pianificato, consuntivato e residuo per voce"),
    ).toBeInTheDocument();
    const row = screen.getByText("Canone Organico").closest("tr")!;
    row.focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByText("Analisi")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nuovo canone" })).not.toBeInTheDocument();
  });

  it("applica filtri e abilita CRUD con canone.manage", async () => {
    const user = userEvent.setup();
    renderPage(["canone.manage"]);
    await screen.findByText("Canone Organico");
    const callsBeforeFilter = getMock.mock.calls.length;
    const search = screen.getByLabelText("Ricerca");
    await user.type(search, "CAN");
    expect(search).toHaveValue("CAN");
    expect(getMock.mock.calls.length).toBe(callsBeforeFilter);
    await user.selectOptions(screen.getByLabelText("Dominio"), "EA");
    await user.click(screen.getByRole("button", { name: "Applica filtri" }));
    await waitFor(() => expect(getMock.mock.calls.length).toBeGreaterThan(callsBeforeFilter));
    expect(getMock.mock.calls.at(-1)?.[0]).toContain("search=CAN");
    expect(getMock.mock.calls.at(-1)?.[0]).toContain("office=EA");
    expect(screen.getByRole("button", { name: "Nuovo canone" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Modifica" })).toBeInTheDocument();
  });

  it("modifica l'attività inline ed evidenzia l'eliminazione", async () => {
    const user = userEvent.setup();
    renderPage(["canone.manage"]);
    await user.click(await screen.findByRole("button", { name: /Analisi/ }));
    expect(screen.getByRole("tab", { name: "Panoramica" })).toHaveAttribute("data-state", "active");
    await user.click(screen.getByRole("tab", { name: "Consuntivi" }));
    expect(screen.getByText("Nessun consuntivo registrato.")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Panoramica" }));
    const editButtons = await screen.findAllByRole("button", { name: "Modifica attività" });
    expect(editButtons.length).toBeGreaterThan(0);
    await user.click(editButtons[0]!);
    expect(screen.getByLabelText("Titolo attività in modifica")).toHaveValue("Analisi");
    expect(screen.getByLabelText("Giornate riservate in modifica")).toHaveValue(50);
    expect(screen.queryByRole("button", { name: "Aggiungi attività" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "ELIMINA" })[0]!).toHaveClass("bg-red-700");
  });

  it("filtra l'elenco delle attività per dominio al click su Applica filtri", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Canone Organico");

    // Inizialmente entrambe le attività sono visibili
    expect(await screen.findByText("Analisi")).toBeInTheDocument();
    expect(screen.getByText("Disegno Solution")).toBeInTheDocument();

    // Seleziona dominio EA e applica i filtri
    await user.selectOptions(screen.getByLabelText("Dominio"), "EA");
    await user.click(screen.getByRole("button", { name: "Applica filtri" }));

    // Solo l'attività EA deve essere visibile nell'elenco
    await waitFor(() => {
      expect(screen.getByText("Analisi")).toBeInTheDocument();
      expect(screen.queryByText("Disegno Solution")).not.toBeInTheDocument();
    });
    expect(screen.getByText(/Filtro dominio:/)).toBeInTheDocument();

    // Seleziona un dominio senza attività (es. CROSS)
    await user.selectOptions(screen.getByLabelText("Dominio"), "CROSS");
    await user.click(screen.getByRole("button", { name: "Applica filtri" }));

    await waitFor(() => {
      expect(screen.queryByText("Analisi")).not.toBeInTheDocument();
      expect(screen.queryByText("Disegno Solution")).not.toBeInTheDocument();
      expect(
        screen.getByText("Nessuna attività trovata per i filtri selezionati."),
      ).toBeInTheDocument();
    });

    // Clicca Azzera: tornano visibili entrambe le attività
    await user.click(screen.getByRole("button", { name: "Azzera" }));
    await waitFor(() => {
      expect(screen.getByText("Analisi")).toBeInTheDocument();
      expect(screen.getByText("Disegno Solution")).toBeInTheDocument();
    });
  });
});
