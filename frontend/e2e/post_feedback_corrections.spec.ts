import { expect, test, type Page } from "@playwright/test";

const ADMIN_USER = process.env.E2E_USERNAME ?? "demo_admin";
const ADMIN_PASS = process.env.E2E_PASSWORD ?? "Demo-Local-2026!";

async function login(page: Page) {
  await page.goto("/");
  const sessionResponse = await page.request.get("/api/v1/auth/session");
  if (sessionResponse.ok()) {
    const session = await sessionResponse.json();
    if (session.username === ADMIN_USER) return;
    await page.request.post("/api/v1/auth/logout");
    await page.context().clearCookies();
    await page.goto("/");
  }
  await page.locator("#username").fill(ADMIN_USER);
  await page.locator("#password").fill(ADMIN_PASS);
  await page.getByRole("button", { name: "Accedi" }).click();
  await expect(page.getByRole("button", { name: "Esci" })).toBeVisible({ timeout: 15_000 });
}

test.describe("Correzioni post-feedback", () => {
  test.beforeEach(async ({ page }) => login(page));

  test("dashboard espone solo fatturazioni del mese con fine mese convenzionale", async ({
    page,
  }) => {
    const response = await page.request.get("/api/v1/dashboard");
    expect(response.ok()).toBeTruthy();
    const dashboard = await response.json();
    const generatedAt = new Date(`${dashboard.generato_il}T00:00:00Z`);
    const expectedMonth = generatedAt.getUTCMonth();
    const expectedYear = generatedAt.getUTCFullYear();
    const expectedMonthEnd = new Date(Date.UTC(expectedYear, expectedMonth + 1, 0))
      .toISOString()
      .slice(0, 10);

    for (const billing of dashboard.prossime_fatturazioni.results) {
      const planned = new Date(`${billing.data_pianificata}T00:00:00Z`);
      expect(planned.getUTCFullYear()).toBe(expectedYear);
      expect(planned.getUTCMonth()).toBe(expectedMonth);
      expect(billing.data_fatturazione).toBe(expectedMonthEnd);
    }
    expect(dashboard.prossime_fatturazioni.results.length).toBeLessThanOrEqual(
      dashboard.prossime_fatturazioni.count,
    );
  });

  test("grafico costi supporta Top N, ricerca e tooltip custom", async ({ page }) => {
    await page.goto("/analisi-costi");
    await expect(page.getByRole("heading", { name: "Costi per progetto" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByLabel("Numero di progetti")).toHaveValue("10");
    await page.getByLabel("Numero di progetti").selectOption("5");
    await expect(page.getByRole("table", { name: /Riepilogo accessibile/ })).toBeVisible();

    const firstProject = await page
      .getByRole("table", { name: /Riepilogo accessibile/ })
      .locator("tbody tr")
      .first()
      .locator("td")
      .first()
      .textContent();
    expect(firstProject).toBeTruthy();
    await page.getByLabel("Cerca progetto").fill(firstProject?.slice(0, 5) ?? "");
    await expect(page.getByRole("table", { name: /Riepilogo accessibile/ })).toContainText(
      firstProject ?? "",
    );

    const bar = page.locator(".recharts-bar-rectangle path").first();
    await bar.hover();
    const tooltip = page.getByTestId("chart-tooltip");
    await expect(tooltip).toBeVisible();
    await expect(tooltip).toHaveCSS("background-color", "rgb(15, 23, 42)");
    await expect(tooltip).toContainText("Costo");
  });

  test("reset è assente dagli altri tab e presente solo in Configurazione", async ({ page }) => {
    await page.goto("/amministrazione");
    await expect(page.getByRole("heading", { name: "Amministrazione" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("open-delete-db-dialog-btn")).toHaveCount(0);
    await page.getByRole("tab", { name: "Utenti" }).click();
    await expect(page.getByTestId("open-delete-db-dialog-btn")).toHaveCount(0);
    await page.getByRole("tab", { name: "Ruoli e privilegi" }).click();
    await expect(page.getByTestId("open-delete-db-dialog-btn")).toHaveCount(0);
    await page.getByRole("tab", { name: "Configurazione" }).click();
    await expect(
      page.getByRole("heading", { name: "Attenzione - Reset Completo DB" }),
    ).toBeVisible();
    await page.getByTestId("open-delete-db-dialog-btn").click();
    await expect(
      page.getByRole("heading", { name: "Sei sicuro di voler eliminare il DB?" }),
    ).toBeVisible();
  });
});
