import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
  status: { consuntivato: "25.0000", forecast: "75.0000" },
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
    await waitFor(() => expect(getMock.mock.calls.length).toBeGreaterThan(callsBeforeFilter));
    expect(screen.getByRole("button", { name: "Nuovo canone" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Modifica" })).toBeInTheDocument();
  });
});
