import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WalletPage } from "@/features/wallet/WalletPage";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  ApiError: class ApiError extends Error {},
}));
let capabilities = ["wallet.edit", "accounting.adjust"];
vi.mock("@/features/auth/session", () => ({
  useSession: () => ({
    session: {
      username: "test",
      roles: [],
      capabilities,
      is_admin: false,
      can_write: false,
    },
  }),
}));

const open = {
  id: "open",
  version: 1,
  riferimento: null,
  origine: "IM26-OPEN",
  origine_titolo: "Origine aperta",
  destinazione: "IM26-OPEN",
  destinazione_titolo: "Attività aperta",
  tipo_attivita: "ATTIVITA",
  architetto: "Mario Rossi",
  allocato: "10.0000",
  consumato: "4.0000",
  disponibile: "6.0000",
  residuo_allocazione: "6.0000",
  residuo_spendibile_origine: "3.0000",
  validita_origine: "VALIDO",
  scadenza_origine: "2027-12-31",
  stato: "APERTA",
  stato_operativo: "IN_CORSO" as const,
};
const closed = {
  ...open,
  id: "closed",
  origine: "IM26-CLOSED",
  destinazione: "ACT-CLOSED",
  destinazione_titolo: "Attività chiusa",
  stato: "CHIUSA",
  stato_operativo: "CHIUSA" as const,
};
const balance = {
  anno: new Date().getFullYear(),
  allocato: "20.0000",
  totale_allocato: "20.0000",
  consumato: "8.0000",
  consumato_allocazioni: "8.0000",
  disponibile: "12.0000",
  disponibile_su_allocazioni: "12.0000",
  capacita_totale_origini: "20.0000",
  capienza_wallet_potenziale: "20.0000",
  residuo_wallet_non_allocato: "10.0000",
  unallocated_capacity: "10.0000",
  residui_validi_non_allocati: "3.0000",
  residui_in_scadenza: "7.2500",
  residui_scaduti: "2.0000",
  residui_potenziali_da_verificare: "1.0000",
  dettaglio_residui: {
    VALIDO: { giornate: "3.0000", progetti: [] },
    IN_SCADENZA: {
      giornate: "7.2500",
      progetti: [{ codice: "IM25-EXP", giornate: "7.2500", scade_il: "2026-12-31", motivo: "" }],
    },
    SCADUTO: { giornate: "2.0000", progetti: [] },
    DA_VERIFICARE: { giornate: "1.0000", progetti: [] },
  },
};
const detail = {
  id: "open",
  version: 1,
  external_ref: null,
  allocated_days: "10.0000",
  consumed_days: "4.0000",
  available_days: "6.0000",
  residuo_allocazione: "6.0000",
  residuo_spendibile_origine: "3.0000",
  validita_origine: "VALIDO",
  scadenza_origine: "2027-12-31",
  status: "APERTA",
  stato_operativo: "IN_CORSO",
  notes: "nota",
  assignee: null,
  architetto: "Mario Rossi",
  source_project_code: "IM26-OPEN",
  source_project_title: "Origine aperta",
  activity_code: "ACT-OPEN",
  activity_title: "Attività aperta",
  year: new Date().getFullYear(),
  funding: [
    {
      ordine: 1,
      progetto_origine: "IM25-OLD",
      anno_provenienza: 2025,
      riservato_iniziale: "7.0000",
      impegnato: "7.0000",
      consumato: "4.0000",
    },
    {
      ordine: 2,
      progetto_origine: "IM26-NEW",
      anno_provenienza: 2026,
      riservato_iniziale: "3.0000",
      impegnato: "3.0000",
      consumato: "0.0000",
    },
  ],
};

function arrange() {
  vi.mocked(api.get).mockImplementation((path: string) => {
    if (path.endsWith("/flow")) return Promise.resolve({ results: [open, closed] });
    if (path.endsWith("/assignees")) return Promise.resolve({ results: [] });
    if (path.includes("/allocations/open/")) return Promise.resolve(detail);
    if (path.includes("allocation-options"))
      return Promise.resolve({
        projects: [
          {
            id: "source-1",
            code: "IM26-SOURCE",
            title: "Origine",
            year: new Date().getFullYear(),
            available_days: "8.0000",
            validity: "VALIDO",
            expires_on: "2027-12-31",
            usable: true,
          },
        ],
        activities: [{ id: "activity-1", code: "ACT-1", title: "Attività nuova" }],
        assignees: [{ id: "person-1", name: "Mario Rossi" }],
        unallocated_capacity: "10.0000",
        potential_wallet_capacity: "20.0000",
      });
    return Promise.resolve(balance);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <WalletPage />
    </QueryClientProvider>,
  );
  return { client, ...view };
}

describe("WalletPage Tranche C", () => {
  beforeEach(() => {
    capabilities = ["wallet.edit", "accounting.adjust"];
    vi.clearAllMocks();
  });

  it("non sostituisce con zero una capacita non disponibile", async () => {
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path.endsWith("/flow") || path.endsWith("/assignees"))
        return Promise.resolve({ results: [] });
      return Promise.resolve({
        ...balance,
        capacita_totale_origini: undefined,
        capienza_wallet_potenziale: undefined,
        residuo_wallet_non_allocato: undefined,
        unallocated_capacity: undefined,
      });
    });
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <WalletPage />
      </QueryClientProvider>,
    );
    const capacity = await screen.findByText("Capacità Monte Wallet");
    expect(capacity.closest("article")).toHaveTextContent("–");
    expect(capacity.closest("article")).not.toHaveTextContent("0,00 gg");
  });

  it("mostra per default solo in corso e consente di filtrare le chiuse", async () => {
    arrange();
    expect(await screen.findByText("Attività aperta")).toBeInTheDocument();
    expect(screen.getByText("IM26-OPEN")).toBeInTheDocument();
    expect(screen.queryByText("IM26-OPEN → IM26-OPEN")).not.toBeInTheDocument();
    expect(screen.queryByText(/ACT-CLOSED/)).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Stato allocazione"), "CHIUSA");
    expect(await screen.findByText(/ACT-CLOSED/)).toBeInTheDocument();
    expect(screen.queryByText("Attività aperta")).not.toBeInTheDocument();
  });

  it("seleziona la riga con tastiera e distingue i residui", async () => {
    arrange();
    const row = await screen.findByTestId("allocation-row-open");
    fireEvent.keyDown(row, { key: "Enter" });
    expect(await screen.findByText("Residuo spendibile origine")).toBeInTheDocument();
    expect(screen.getAllByText("Residuo allocazione").length).toBeGreaterThan(0);
    expect(screen.getByText("IM25-EXP")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Riduci al consumato" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Chiudi dettaglio" }));
    expect(screen.queryByText("Residuo spendibile origine")).not.toBeInTheDocument();
  });

  it("permette il dettaglio read-only senza wallet.edit", async () => {
    capabilities = [];
    arrange();
    await userEvent.click(await screen.findByTestId("allocation-row-open"));
    expect(await screen.findByText(/Consultazione/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Salva" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nuovo utilizzo" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Elimina allocazione" })).not.toBeInTheDocument();
  });

  it("espone creazione FIFO e comando delete agli autorizzati", async () => {
    arrange();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Nuovo utilizzo" }));
    expect(screen.getByText("Monte Wallet FIFO")).toBeInTheDocument();
    expect(screen.getByText(/attribuite automaticamente in FIFO/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Annulla" }));
    await user.click(await screen.findByTestId("allocation-row-open"));
    expect(await screen.findByRole("button", { name: "Elimina allocazione" })).toBeInTheDocument();
  });

  it("salva con pulsante verde e invalida flow, KPI, sommari e opzioni", async () => {
    const { client } = arrange();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    vi.mocked(api.patch).mockResolvedValue({ ...detail, notes: "aggiornata", version: 2 });
    await userEvent.click(await screen.findByTestId("allocation-row-open"));
    const save = await screen.findByRole("button", { name: "Salva" });
    expect(save).toHaveClass("bg-emerald-700");
    await userEvent.clear(screen.getByLabelText("Note"));
    await userEvent.type(screen.getByLabelText("Note"), "aggiornata");
    await userEvent.click(save);
    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({
        queryKey: ["wallet", "flow", new Date().getFullYear()],
      }),
    );
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ["wallet", "balance", new Date().getFullYear()],
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ["wallet", "assignees", new Date().getFullYear()],
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["wallet", "allocation-options"] });
  });

  it("rettifica il consumato totale e mostra le fonti FIFO in tabella", async () => {
    arrange();
    vi.mocked(api.patch).mockResolvedValue({ ...detail, consumed_days: "5.5000", version: 2 });
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("allocation-row-open"));
    expect(await screen.findByText(/Ordine effettivo di erosione/)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Progetto origine" })).toBeInTheDocument();
    expect(screen.getByText("IM25-OLD")).toBeInTheDocument();
    expect(screen.getByText("IM26-NEW")).toBeInTheDocument();

    const consumed = screen.getByLabelText("Giornate consumate totali");
    await user.clear(consumed);
    await user.type(consumed, "5.5");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        "/wallet/allocations/open/",
        expect.objectContaining({ adjust_consumed_to: "5.5" }),
        expect.anything(),
      ),
    );
  });

  it("mostra i 5 KPI a due livelli e badge Origine: Monte Wallet per voce generica", async () => {
    const genericFlow = {
      ...open,
      id: "generic-1",
      origine: "WALLET-GENERALE",
      origine_titolo: "Monte Wallet (pool generico)",
      destinazione: "ACT-X",
      destinazione_titolo: "ATTIVITÀ X",
    };
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path.endsWith("/flow")) return Promise.resolve({ results: [genericFlow] });
      if (path.endsWith("/assignees")) return Promise.resolve({ results: [] });
      if (path.includes("balance"))
        return Promise.resolve({
          ...balance,
          capacita_totale_origini: "7.0000",
          residuo_wallet_non_allocato: "2.0000",
          totale_allocato: "5.0000",
          disponibile_su_allocazioni: "5.0000",
          consumato_allocazioni: "0.0000",
        });
      return Promise.resolve({ projects: [], activities: [], assignees: [] });
    });

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <WalletPage />
      </QueryClientProvider>,
    );

    // Verifica 5 KPI
    expect(await screen.findByText("Capacità Monte Wallet")).toBeInTheDocument();
    expect(screen.getByText("Residuo Wallet non allocato")).toBeInTheDocument();
    expect(screen.getByText("Totale allocato a voci")).toBeInTheDocument();
    expect(screen.getByText("Residuo disponibile sulle voci")).toBeInTheDocument();
    expect(screen.getByText("Consuntivato su voci")).toBeInTheDocument();

    // Verifica voce e badge origine
    expect(await screen.findByText("ATTIVITÀ X")).toBeInTheDocument();
    expect(screen.getByText("Origine: Monte Wallet")).toBeInTheDocument();
  });

  it("permette la creazione di una voce generica dal monte wallet con nuova attività al volo", async () => {
    arrange();
    vi.mocked(api.post).mockResolvedValue({ id: "new-alloc", version: 1 });
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Nuovo utilizzo" }));
    expect(screen.getByText("Monte Wallet FIFO")).toBeInTheDocument();

    // Clic su "+ Nuova attività"
    await user.click(screen.getByText("+ Nuova attività"));
    const titleInput = screen.getByPlaceholderText("Nome attività");
    await user.type(titleInput, "ATTIVITÀ X");

    // Selezione assegnatario
    await user.selectOptions(screen.getByLabelText(/Assegnatario/), "person-1");

    // Inserimento giornate
    const daysInput = screen.getByLabelText(/Giornate da riservare/);
    await user.type(daysInput, "5.0000");

    // Invio
    await user.click(screen.getByRole("button", { name: "Crea utilizzo" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/allocations", {
        year: new Date().getFullYear(),
        assignee: "person-1",
        allocated_days: "5",
        new_activity_title: "ATTIVITÀ X",
        notes: "",
      }),
    );
  });
});
