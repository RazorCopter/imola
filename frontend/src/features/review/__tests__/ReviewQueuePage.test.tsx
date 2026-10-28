import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, it, expect } from "vitest";
import { ReviewQueuePage } from "../ReviewQueuePage";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock("@/features/auth/session", () => ({
  useSession: () => ({ session: { roles: [], capabilities: [], is_admin: false } }),
}));
it("filtra la coda senza nascondere lo stato vuoto della ricerca", async () => {
  vi.mocked(api.get).mockResolvedValue({
    count: 1,
    results: [
      {
        id: "1",
        codice: "IM-01",
        titolo: "Progetto alfa",
        motivo_revisione: "Verificare chiusura",
        stato_consuntivazione: "ATTIVO",
        data_chiusura: null,
        data_fine_prevista: null,
      },
    ],
  });
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ReviewQueuePage />
    </QueryClientProvider>,
  );
  expect(await screen.findByText("Progetto alfa")).toBeInTheDocument();
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Cerca nella coda di revisione"), "inesistente");
  expect(screen.getByText("Nessun progetto corrisponde alla ricerca")).toBeInTheDocument();
  await user.clear(screen.getByLabelText("Cerca nella coda di revisione"));
  expect(screen.getByText("Progetto alfa")).toBeInTheDocument();
});
