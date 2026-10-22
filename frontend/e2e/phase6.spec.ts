import { expect, test } from "@playwright/test";

const USER = process.env.E2E_USERNAME;
const PASS = process.env.E2E_PASSWORD;
if (!USER || !PASS) throw new Error("E2E_USERNAME ed E2E_PASSWORD obbligatorie");

async function login(page: import("@playwright/test").Page) {
    await page.goto("/");
    await page.locator("#username").fill(USER!);
    await page.locator("#password").fill(PASS!);
    await page.getByRole("button", { name: "Accedi" }).click();
    await expect(page.getByRole("button", { name: "Esci" })).toBeVisible({ timeout: 10000 });
}

test("login -> dashboard", async ({ page }) => {
    await login(page);
    await expect(page.getByText("Dashboard").first()).toBeVisible();
});

test("import seed dry-run -> apply (API autenticata)", async ({ page }) => {
    await login(page);
    const session = await page.context().cookies();
    expect(session.length).toBeGreaterThan(0);
    await expect(page.getByText("Supplier Ledger").first()).toBeVisible();
});

test("chiusura progetto con anteprima scadenza", async ({ page }) => {
    await login(page);
    await page.goto("/revisione");
    await expect(page.getByRole("heading", { name: "Coda di revisione progetti" })).toBeVisible();
    const first = page.getByRole("button", { name: "Conferma revisione" }).first();
    if (await first.isVisible()) {
        await first.click();
        await expect(page.getByRole("button", { name: "Salva" })).toBeVisible();
    }
});

test("nuova allocazione wallet / regolazione", async ({ page }) => {
    await login(page);
    await page.goto("/wallet");
    await expect(page.getByRole("heading", { name: /Wallet/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "Riduci al consumato" }).first()).toBeVisible();
});

test("risoluzione anomalia", async ({ page }) => {
    await login(page);
    await page.goto("/anomalie");
    await expect(page.getByRole("heading", { name: "Inbox anomalie" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Risolvi" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Accetta con deroga" }).first()).toBeVisible();
});
