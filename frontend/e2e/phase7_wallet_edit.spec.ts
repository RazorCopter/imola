import { expect, test, type Page } from "@playwright/test";

const ADMIN_USER = process.env.E2E_USERNAME ?? "demo_admin";
const ADMIN_PASS = process.env.E2E_PASSWORD ?? "Demo-Local-2026!";
const FORNITORE_USER = "demo_fornitore";
const FORNITORE_PASS = "Demo-Local-2026!";

async function login(page: Page, username = ADMIN_USER, password = ADMIN_PASS) {
  await page.goto("/");
  const sessionRes = await page.request.get("/api/v1/auth/session");
  if (sessionRes.ok()) {
    const sessionData = await sessionRes.json();
    if (sessionData.username === username) return;
    await page.request.post("/api/v1/auth/logout");
    await page.context().clearCookies();
    await page.goto("/");
  }
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Accedi" }).click();
  await expect(page.getByRole("button", { name: "Esci" })).toBeVisible({ timeout: 15000 });
}

test.describe("Tranche C: pannello operativo Wallet", () => {
  test("admin seleziona una riga e vede editing inline", async ({ page }) => {
    await login(page);
    await page.goto("/wallet");
    await expect(page.getByRole("heading", { name: /Wallet/ })).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("button", { name: "Nuova allocazione" })).toBeVisible();
    await page.getByRole("button", { name: "Nuova allocazione" }).click();
    await expect(page.getByText(/residuo spendibile del progetto origine/i)).toBeVisible();
    await page.getByRole("button", { name: "Annulla" }).click();
    const rows = page.locator("tr[data-testid^='allocation-row-']");
    if ((await rows.count()) > 0) {
      await rows.first().click();
      await expect(page.getByLabel("Dettaglio allocazione")).toBeVisible();
      await expect(page.getByRole("button", { name: "Salva" })).toHaveClass(/bg-emerald-600/);
      await expect(page.getByRole("button", { name: "Elimina allocazione" })).toBeVisible();
      await page.getByRole("button", { name: "Elimina allocazione" }).click();
      await expect(page.getByRole("button", { name: "Elimina definitivamente" })).toBeDisabled();
      await page.getByRole("button", { name: "Annulla" }).click();
      await expect(page.getByRole("button", { name: "Riduci al consumato" })).toHaveCount(0);
    }
  });

  test("fornitore consulta il dettaglio ma non può salvare", async ({ page }) => {
    await login(page, FORNITORE_USER, FORNITORE_PASS);
    await page.goto("/wallet");
    const rows = page.locator("tr[data-testid^='allocation-row-']");
    if ((await rows.count()) > 0) {
      await rows.first().press("Enter");
      await expect(page.getByText(/Consultazione/)).toBeVisible();
      await expect(page.getByRole("button", { name: "Salva" })).toHaveCount(0);
    }
  });
});
