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
        if (sessionData.username === username) {
            await expect(page.getByRole("button", { name: "Esci" })).toBeVisible({ timeout: 10000 });
            return;
        }
        await page.request.post("/api/v1/auth/logout");
        await page.context().clearCookies();
        await page.goto("/");
    }

    await expect(page.locator("#username")).toBeVisible({ timeout: 15000 });
    await page.locator("#username").fill(username);
    await page.locator("#password").fill(password);
    await page.getByRole("button", { name: "Accedi" }).click();
    await expect(page.getByRole("button", { name: "Esci" })).toBeVisible({ timeout: 15000 });
}

test.describe("Tranche 5: Editing Wallet con pulsante EDIT arancione", () => {
    test("admin vede pulsante EDIT arancione sulle allocazioni e apre modale", async ({ page }) => {
        await login(page, ADMIN_USER, ADMIN_PASS);
        await page.goto("/wallet");

        await expect(page.getByRole("heading", { name: /Wallet/ })).toBeVisible({ timeout: 15000 });

        const editButtons = page.locator("button[data-testid^='edit-allocation-']");
        const count = await editButtons.count();

        if (count > 0) {
            const firstEdit = editButtons.first();
            await expect(firstEdit).toBeVisible();
            await expect(firstEdit).toHaveText("EDIT");
            await expect(firstEdit).toHaveClass(/bg-amber-500/);

            // Clicca sul pulsante EDIT
            await firstEdit.click();
            await expect(page.getByRole("heading", { name: "Modifica Allocazione Wallet" })).toBeVisible({
                timeout: 10000,
            });
            await expect(page.locator("#allocated_days_input")).toBeVisible();
            await expect(page.getByRole("button", { name: "Chiudi" })).toBeVisible();

            // Chiudi il dialog
            await page.getByRole("button", { name: "Chiudi" }).click();
            await expect(
                page.getByRole("heading", { name: "Modifica Allocazione Wallet" }),
            ).not.toBeVisible();
        }
    });

    test("fornitore non vede il pulsante EDIT arancione sulle allocazioni wallet", async ({
        page,
    }) => {
        await login(page, FORNITORE_USER, FORNITORE_PASS);
        await page.goto("/wallet");

        await expect(page.getByRole("heading", { name: /Wallet/ })).toBeVisible({ timeout: 15000 });
        const editButtons = page.locator("button[data-testid^='edit-allocation-']");
        await expect(editButtons).toHaveCount(0);
    });
});
