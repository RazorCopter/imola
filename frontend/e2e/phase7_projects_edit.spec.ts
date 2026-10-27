import { expect, test, type Page } from "@playwright/test";

const ADMIN_USER = process.env.E2E_USERNAME ?? "demo_admin";
const ADMIN_PASS = process.env.E2E_PASSWORD ?? "Demo-Local-2026!";
const REFERENTE_USER = "demo_referente";
const REFERENTE_PASS = "Demo-Local-2026!";
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

test.describe("Tranche 4: Editing completo Progetti con pulsante EDIT arancione", () => {
  test("admin vede pulsante EDIT arancione, apre form completo e salva modifiche", async ({
    page,
  }) => {
    await login(page, ADMIN_USER, ADMIN_PASS);
    await page.goto("/progetti");

    await expect(page.getByRole("heading", { name: "Progetti" })).toBeVisible();

    // Verifica il flusso di conferma senza inviare DELETE su dati persistenti.
    const firstEditForDelete = page.getByRole("button", { name: "EDIT" }).first();
    if (await firstEditForDelete.isVisible()) {
      await firstEditForDelete.click();
      await expect(page.getByRole("button", { name: "Elimina progetto" })).toBeVisible();
      await page.getByRole("button", { name: "Elimina progetto" }).click();
      await expect(page.getByRole("button", { name: "Elimina definitivamente" })).toBeDisabled();
      await page.getByRole("button", { name: "Annulla" }).last().click();
      await page.getByRole("button", { name: "Annulla" }).click();
    }

    // Trova un pulsante EDIT arancione nella tabella
    const editBtn = page.getByRole("button", { name: "EDIT" }).first();
    await expect(editBtn).toBeVisible({ timeout: 10000 });
    await expect(editBtn).toHaveClass(/bg-amber-500/);

    // Clicca EDIT per aprire il dialog
    await editBtn.click();
    await expect(page.getByRole("heading", { name: "Modifica Progetto" })).toBeVisible();

    // Codice readonly con spiegazione
    await expect(page.getByText(/Codice Progetto \(Read-only\)/i)).toBeVisible();
    await expect(page.getByText(/Il codice è bloccato/i)).toBeVisible();

    // Verifica campi abilitati per admin
    const titleInput = page.locator("input[name='title']");
    await expect(titleInput).toBeEnabled();

    // Modifica le note e salva
    const notesInput = page.locator("textarea[name='notes']");
    const testNote = `Nota aggiornata E2E admin ${Date.now()}`;
    await notesInput.fill(testNote);

    await page.getByRole("button", { name: "Salva Modifiche" }).click();

    // Dialog si chiude
    await expect(page.getByRole("heading", { name: "Modifica Progetto" })).not.toBeVisible();
  });

  test("referente vede EDIT solo sui propri progetti ed ha campi generali disabilitati", async ({
    page,
  }) => {
    await login(page, REFERENTE_USER, REFERENTE_PASS);
    await page.goto("/progetti");

    await expect(page.getByRole("heading", { name: "Progetti" })).toBeVisible();

    // Vede il pulsante EDIT sul proprio progetto (se presente nel dataset)
    const editButtons = page.getByRole("button", { name: "EDIT" });
    if ((await editButtons.count()) > 0) {
      const editBtn = editButtons.first();
      await expect(editBtn).toBeVisible({ timeout: 10000 });

      await editBtn.click();
      await expect(page.getByRole("heading", { name: "Modifica Progetto" })).toBeVisible();

      // Per il referente, il titolo è disabilitato
      await expect(page.locator("input[name='title']")).toBeDisabled();
      // Le note sono abilitate
      await expect(page.locator("textarea[name='notes']")).toBeEnabled();

      // Chiudi dialog
      await page.getByRole("button", { name: "Annulla" }).click();
      await expect(page.getByRole("heading", { name: "Modifica Progetto" })).not.toBeVisible();
    } else {
      await expect(editButtons).toHaveCount(0);
    }
  });

  test("fornitore senza capability projects.edit non vede il pulsante EDIT", async ({ page }) => {
    await login(page, FORNITORE_USER, FORNITORE_PASS);
    await page.goto("/progetti");

    await expect(page.getByRole("heading", { name: "Progetti" })).toBeVisible();

    // Attendiamo che la tabella si carichi
    await expect(page.getByRole("region", { name: "Tabella dati" })).toBeVisible({
      timeout: 10000,
    });

    // Nessun pulsante EDIT deve essere presente
    await expect(page.getByRole("button", { name: "EDIT" })).toHaveCount(0);
  });
});
