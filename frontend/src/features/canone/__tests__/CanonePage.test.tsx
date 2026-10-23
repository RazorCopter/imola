import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CanonePage } from "@/features/canone/CanonePage";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn() } }));
const getMock = vi.mocked(api.get);

const status = {
  semestre: "2026-S1",
  monte: "100.0000",
  consuntivato: "10.0000",
  target_alla_data: "20.0000",
  delta: "10.0000",
  forecast: "90.0000",
  percentuale_forecast: "90.0000",
  proiezione: "90.0000",
  giornate_non_usate_previste: "10.0000",
  formula_target: "formula",
  per_ufficio: {},
  burndown: [],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <CanonePage />
    </QueryClientProvider>,
  );
}

describe("CanonePage", () => {
  beforeEach(() => getMock.mockReset());

  it("seleziona il default backend e preserva la scelta manuale al reload", async () => {
    getMock.mockImplementation((url) =>
      Promise.resolve(
        url === "/canoni"
          ? {
              default_canone_id: "old",
              results: [
                {
                  id: "new",
                  semestre: "2026-S2",
                  progetto_codice: "IM-S2",
                  progetto_titolo: "S2",
                  ultimo_movimento: "2026-05-01",
                },
                {
                  id: "old",
                  semestre: "2026-S1",
                  progetto_codice: "IM-S1",
                  progetto_titolo: "S1",
                  ultimo_movimento: "2026-06-01",
                },
              ],
            }
          : status,
      ),
    );
    const user = userEvent.setup();
    renderPage();

    const select = await screen.findByRole("combobox", { name: "Semestre" });
    expect(select).toHaveValue("old");
    expect(screen.getByRole("heading", { name: "Organico Allargato" })).toBeInTheDocument();

    await user.selectOptions(select, "new");
    expect(select).toHaveValue("new");
    await waitFor(() => expect(getMock).toHaveBeenCalledWith("/canoni/new/status"));
  });

  it("mostra empty state quando non esistono periodi", async () => {
    getMock.mockResolvedValue({ default_canone_id: null, results: [] });
    renderPage();

    expect(
      await screen.findByText("Nessun periodo di Organico Allargato disponibile"),
    ).toBeInTheDocument();
  });
});
