import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, it, expect } from "vitest";
import { AnomaliesPage } from "../AnomaliesPage";
import { api } from "@/lib/api";
vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn() } }));
let capabilities: string[] = [];
vi.mock("@/features/auth/session", () => ({
  useSession: () => ({ session: { roles: [], capabilities, is_admin: false } }),
}));
it("gestisce lo stato vuoto e applica il filtro senza abilitare azioni non consentite", async () => {
  vi.mocked(api.get).mockResolvedValue({ results: [] });
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <AnomaliesPage />
    </QueryClientProvider>,
  );
  expect(await screen.findByText("Nessuna anomalia trovata")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Esegui controlli" })).not.toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText("Filtra anomalie per stato"), "RISOLTA");
  expect(vi.mocked(api.get)).toHaveBeenLastCalledWith("/anomalies?stato=RISOLTA");
});

it("richiede una data per la deroga e invia quella scelta", async () => {
  capabilities = ["accounting.adjust"];
  vi.mocked(api.get).mockResolvedValue({
    results: [
      {
        id: "1",
        external_ref: "A1",
        codice_regola: "A1",
        severita: "ALTA",
        ambito: "PROGETTO",
        descrizione: "Verifica",
        stato: "APERTA",
        progetto: null,
        contesto: {},
        azione_suggerita: "",
        nota_risoluzione: "",
        sostituita_da: null,
      },
    ],
  });
  vi.mocked(api.post).mockResolvedValue({});
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <AnomaliesPage />
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Accetta con deroga" }));
  expect(screen.getByRole("button", { name: "Conferma deroga" })).toBeDisabled();
  await user.type(screen.getByLabelText("Scadenza deroga"), "2027-06-30");
  await user.click(screen.getByRole("button", { name: "Conferma deroga" }));
  expect(vi.mocked(api.post)).toHaveBeenCalledWith("/anomalies/1/accept", {
    nota: "Deroga approvata con scadenza",
    fino_al: "2027-06-30",
  });
});
