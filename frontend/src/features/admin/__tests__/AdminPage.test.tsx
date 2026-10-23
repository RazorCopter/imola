import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminPage } from "@/features/admin/AdminPage";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  API_BASE: "/api/v1",
  api: { get: vi.fn(), post: vi.fn() },
}));

const getMock = vi.mocked(api.get);
const postMock = vi.mocked(api.post);

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AdminPage />
    </QueryClientProvider>,
  );
}

describe("AdminPage", () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    getMock.mockImplementation((url) =>
      Promise.resolve(
        url === "/admin/imports" ? { results: [] } : { roles: ["Amministratore"], results: [] },
      ),
    );
  });

  it("abilita l'azione verde solo dopo un dry-run valido", async () => {
    postMock.mockResolvedValue({
      mode: "dry-run",
      confirmation_hash: "hash-valido",
      report: { valid: true },
    });
    const user = userEvent.setup();
    const { container } = renderPage();
    const applyButtons = await screen.findAllByRole("button", { name: "Conferma e applica" });

    expect(applyButtons[0]).toBeDisabled();
    expect(applyButtons[0]).toHaveClass("bg-emerald-600", "border-emerald-800");
    expect(screen.getAllByText(/Esegui prima “Valida e simula”/)).toHaveLength(2);

    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    await user.upload(input!, new File(["{}"], "seed.json", { type: "application/json" }));
    const previewButton = screen.getAllByRole("button", { name: "Valida e simula" })[0];
    expect(previewButton).toBeDefined();
    await user.click(previewButton!);

    expect(await screen.findByText(/Anteprima valida/)).toBeInTheDocument();
    expect(applyButtons[0]).toBeEnabled();
  });
});
