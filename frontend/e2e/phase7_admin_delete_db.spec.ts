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

test.describe("Tranche 6: Funzione ELIMINA DB in Amministrazione", () => {
    test("admin vede pulsante rosso ELIMINA DB, apre dialog con controverifica e sblocco con ELIMINA", async ({
        page,
    }) => {
        await login(page, ADMIN_USER, ADMIN_PASS);
        await page.getByRole("link", { name: "Amministrazione" }).click();

        await expect(page.getByRole("heading", { name: "Amministrazione" })).toBeVisible({
            timeout: 15000,
        });

        const openBtn = page.getByTestId("open-delete-db-dialog-btn");
        await expect(openBtn).toBeVisible();
        await expect(openBtn).toHaveText("ELIMINA DB");
        await expect(openBtn).toHaveClass(/bg-danger/);

        // Clicca per aprire il dialog
        await openBtn.click();
        await expect(
            page.getByRole("heading", { name: "Sei sicuro di voler eliminare il DB?" }),
        ).toBeVisible({ timeout: 10000 });

        const input = page.getByTestId("delete-db-confirmation-input");
        const confirmBtn = page.getByTestId("confirm-delete-db-btn");

        await expect(input).toBeVisible();
        await expect(confirmBtn).toBeVisible();
        await expect(confirmBtn).toBeDisabled();

        // Digitazione testo non corrispondente
        await input.fill("elimina");
        await expect(confirmBtn).toBeDisabled();

        await input.fill("ELIMINA");
        await expect(confirmBtn).toBeEnabled();

        // Chiudi il dialog senza eliminare
        await page.getByRole("button", { name: "Annulla" }).click();
        await expect(
            page.getByRole("heading", { name: "Sei sicuro di voler eliminare il DB?" }),
        ).not.toBeVisible();
    });

    test("fornitore non vede il pulsante ELIMINA DB nella sezione admin", async ({ page }) => {
        await login(page, FORNITORE_USER, FORNITORE_PASS);
        await page.goto("/amministrazione");

        const openBtn = page.getByTestId("open-delete-db-dialog-btn");
        await expect(openBtn).toHaveCount(0);
    });
});
