import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminPage } from "@/features/admin/AdminPage";
import { ApiError, api } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    API_BASE: "/api/v1",
    api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

vi.mock("@/features/auth/session", () => ({
  useSession: () => ({
    session: {
      username: "admin",
      full_name: "Admin",
      email: "",
      roles: ["admin"],
      capabilities: ["data.reset", "users.manage", "privileges.manage"],
      is_admin: true,
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
const postMock = vi.mocked(api.post);
const putMock = vi.mocked(api.put);

const users = {
  roles: [
    { key: "admin", label: "Amministratore" },
    { key: "fornitore", label: "Fornitore" },
  ],
  results: [
    {
      id: 2,
      username: "mario",
      first_name: "Mario",
      last_name: "Rossi",
      email: "mario@example.test",
      is_active: true,
      is_staff: false,
      is_superuser: false,
      roles: ["fornitore"],
      last_login: null,
      date_joined: "2026-01-01T00:00:00Z",
    },
  ],
};
const roleCapabilities = {
  capabilities: ["projects.create", "users.manage"],
  reserved: ["users.manage"],
  roles: [
    { key: "admin", label: "Amministratore", capabilities: ["projects.create", "users.manage"] },
    { key: "fornitore", label: "Fornitore", capabilities: ["projects.create"] },
  ],
};

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
    vi.clearAllMocks();
    getMock.mockImplementation((url) =>
      Promise.resolve(
        url === "/admin/imports"
          ? { results: [] }
          : url === "/admin/users"
            ? users
            : roleCapabilities,
      ),
    );
  });

  it("mostra i tre tab e abilita apply solo dopo dry-run", async () => {
    postMock.mockResolvedValue({
      mode: "dry-run",
      confirmation_hash: "hash-valido",
      report: { valid: true },
    });
    const user = userEvent.setup();
    const { container } = renderPage();
    expect(await screen.findByRole("tab", { name: "Utenti" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Ruoli e privilegi" })).toBeVisible();
    const applyButtons = screen.getAllByRole("button", { name: "Conferma e applica" });
    expect(applyButtons[0]).toBeDisabled();
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["{}"], "seed.json", { type: "application/json" }));
    await user.click(screen.getAllByRole("button", { name: "Valida e simula" })[0]!);
    await waitFor(() => expect(applyButtons[0]).toBeEnabled());
  });

  it("apre il modale di creazione e invia il CRUD", async () => {
    postMock.mockResolvedValue({});
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("tab", { name: "Utenti" }));
    expect(screen.getByText("mario")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Crea utente" }));
    expect(screen.getByRole("dialog", { name: "Crea utente" })).toBeVisible();
    await user.type(screen.getByLabelText("Username"), "nuovo");
    await user.type(screen.getByLabelText("Email"), "nuovo@example.test");
    await user.type(screen.getByLabelText("Password iniziale"), "Password-test-123!");
    await user.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith(
        "/admin/users",
        expect.objectContaining({ username: "nuovo" }),
      ),
    );
  });

  it("blocca Admin e capability riservate, salva una capability non riservata", async () => {
    putMock.mockResolvedValue({});
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("tab", { name: "Ruoli e privilegi" }));
    expect(screen.getByLabelText("Amministratore: projects.create")).toBeDisabled();
    expect(screen.getByLabelText("Fornitore: users.manage")).toBeDisabled();
    await user.click(screen.getByLabelText("Fornitore: projects.create"));
    await user.click(screen.getByRole("button", { name: "Salva Fornitore" }));
    await waitFor(() =>
      expect(putMock).toHaveBeenCalledWith("/admin/roles/capabilities", {
        role: "fornitore",
        capabilities: [],
      }),
    );
  });

  it("mostra errori API leggibili", async () => {
    postMock.mockRejectedValue(
      new ApiError({
        type: "about:blank",
        title: "Conflitto",
        status: 409,
        code: "conflict",
        detail: "Username già utilizzato.",
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("tab", { name: "Utenti" }));
    await user.click(screen.getByRole("button", { name: "Crea utente" }));
    await user.type(screen.getByLabelText("Username"), "mario");
    await user.type(screen.getByLabelText("Password iniziale"), "Password-test-123!");
    await user.click(screen.getByRole("button", { name: "Salva" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Username già utilizzato.");
  });

  it("mostra la Zona Pericolosa con pulsante ELIMINA DB e apre il dialog", async () => {
    getMock.mockImplementation((path: string) => {
      if (path === "/admin/reset-data") {
        return Promise.resolve({
          preview: { progetti: 5, consuntivi: 10 },
          total_records: 15,
          confirmation_keyword: "ELIMINA",
          token: "test-token-123",
        });
      }
      if (path === "/admin/imports") return Promise.resolve({ results: [] });
      if (path === "/admin/users") return Promise.resolve(users);
      if (path === "/admin/roles/capabilities") return Promise.resolve(roleCapabilities);
      return Promise.resolve({});
    });

    const user = userEvent.setup();
    renderPage();

    const deleteDbBtn = await screen.findByTestId("open-delete-db-dialog-btn");
    expect(deleteDbBtn).toBeInTheDocument();
    expect(deleteDbBtn).toHaveTextContent("ELIMINA DB");

    await user.click(deleteDbBtn);
    expect(
      await screen.findByRole("heading", { name: /Sei sicuro di voler eliminare il DB\?/i }),
    ).toBeVisible();
    expect(screen.getByTestId("delete-db-confirmation-input")).toBeInTheDocument();
    expect(screen.getByTestId("confirm-delete-db-btn")).toBeDisabled();
  });
});
