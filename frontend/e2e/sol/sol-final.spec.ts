/// <reference lib="dom" />
import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs/promises";
import { installFixtures, routes } from "./fixtures";
const folder = "../outputs/visual-review/sol-final";
const errors = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  const list: string[] = [];
  errors.set(page, list);
  page.on("pageerror", (e) => list.push(e.message));
  page.on("console", (message) => {
    if (
      message.type() === "error" &&
      !/Failed to load resource: the server responded with a status of (503|422)/.test(
        message.text(),
      )
    )
      list.push(message.text());
  });
});
test.afterEach(async ({ page }) => {
  await page.waitForLoadState("networkidle").catch(() => {});
  expect(errors.get(page) ?? []).toEqual([]);
});
async function capture(page: Page, name: string) {
  await fs.mkdir(folder, { recursive: true });
  await page.screenshot({ path: `${folder}/${name}.png`, animations: "disabled" });
}
async function audit(page: Page, name: string) {
  await page.waitForFunction(() =>
    document
      .getAnimations()
      .filter((animation) => animation.effect?.getComputedTiming().iterations !== Infinity)
      .every((animation) => animation.playState !== "running"),
  );
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  await fs.mkdir(folder, { recursive: true });
  await fs.writeFile(`${folder}/${name}-axe.json`, JSON.stringify(result.violations, null, 2));
  await fs.writeFile(
    `${folder}/${name}-axe-summary.json`,
    JSON.stringify(
      {
        date: new Date().toISOString(),
        url: page.url(),
        viewport: page.viewportSize(),
        axe: result.testEngine,
        violations: result.violations.length,
        passes: result.passes.length,
        incomplete: result.incomplete.map((r) => ({ id: r.id, nodes: r.nodes.length })),
        tags: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"],
      },
      null,
      2,
    ),
  );
  expect
    .soft(
      result.violations.map((v) => ({
        id: v.id,
        impact: v.impact,
        nodes: v.nodes.map((n) => n.target),
      })),
    )
    .toEqual([]);
}
for (const [name, path] of routes) {
  test(`${name}: temi, responsive e accessibilita`, async ({ page }) => {
    const { unhandled } = await installFixtures(page);
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    for (const [theme, width, height] of [
      ["dark", 1920, 1080],
      ["dark", 1600, 900],
      ["dark", 1440, 900],
      ["dark", 1366, 768],
      ["dark", 1024, 768],
      ["light", 1440, 900],
    ] as const) {
      await page.setViewportSize({ width, height });

      await page.goto(path);
      await page.locator("main h1").waitFor();
      if ((await page.locator("html").getAttribute("data-theme")) !== theme)
        await page
          .getByRole("button", {
            name: theme === "dark" ? "Tema scuro" : "Tema chiaro",
            exact: true,
          })
          .click();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      await page.waitForLoadState("networkidle");
      expect(
        await page.evaluate<boolean>("document.documentElement.scrollWidth <= innerWidth"),
      ).toBeTruthy();
      await capture(page, `${name}-${theme}-${width}x${height}`);
      if (width === 1440) {
        await audit(page, `${name}-${theme}`);
        if (await page.locator("main").evaluate((e) => e.scrollHeight > e.clientHeight)) {
          await page.locator("main").evaluate((e) => {
            e.scrollTop = e.scrollHeight;
          });
          await capture(page, `${name}-${theme}-bottom`);
          await page.locator("main").evaluate((e) => {
            e.scrollTop = 0;
          });
        }
      }
    }
    expect(errors).toEqual([]);
    expect(unhandled).toEqual([]);
  });
}
test("stati vuoti ed errori per nove sezioni", async ({ browser }) => {
  test.setTimeout(180000);
  for (const mode of ["empty", "error"] as const)
    for (const [name, path] of routes) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const page = await context.newPage();
      await installFixtures(page, mode);
      await page.goto(`http://127.0.0.1:5176${path}`);
      await page.waitForLoadState("networkidle");
      if (mode === "error") await expect(page.getByRole("alert").first()).toBeVisible();
      await capture(page, `${name}-${mode}`);
      await context.close();
    }
});
test("progetti: ricerca, ordinamento, creazione e modifica", async ({ page }) => {
  const { writes, unhandled } = await installFixtures(page);
  await page.goto("/progetti");
  await page.getByPlaceholder("Codice o titolo").fill("inesistente");
  await expect(page.getByText("Nessun progetto corrisponde ai filtri.")).toBeVisible();
  await page.getByRole("button", { name: "Azzera filtri" }).click();
  await page.getByRole("button", { name: "Nuovo progetto", exact: true }).click();
  await page.getByRole("button", { name: "Continua" }).click();
  await expect(page.getByText("Campo obbligatorio").first()).toBeVisible();
  await capture(page, "progetti-validazione");
  await page.getByLabel("Codice", { exact: true }).fill("TEST-NEW");
  await page.getByLabel("Titolo", { exact: true }).fill("Progetto di prova");
  await page.getByLabel("Budget (gg)", { exact: true }).fill("10");
  await page.getByRole("button", { name: "Continua" }).click();
  await page.getByRole("button", { name: "Continua" }).click();
  await page.getByRole("button", { name: "Crea progetto", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(writes.some((w) => w.path === "/projects")).toBeTruthy();
  await page.getByTestId("edit-project-p1").click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await capture(page, "progetti-modifica-dialog");
  await audit(page, "progetti-dialog");
  await page.getByRole("dialog").getByLabel("Titolo", { exact: true }).fill("Titolo modificato");
  await page.getByRole("button", { name: /Salva/ }).last().click();
  await expect
    .poll(() => writes.some((w) => w.path === "/projects/p1" && w.method === "PATCH"))
    .toBeTruthy();
  await page.waitForLoadState("networkidle");
  expect(unhandled).toEqual([]);
});
test("progetto: dettaglio e consuntivo", async ({ page }) => {
  const { writes } = await installFixtures(page);
  await page.goto("/progetti");
  await page
    .getByText("Evoluzione della piattaforma digitale e dei servizi al cliente", { exact: true })
    .click();
  await expect(page).toHaveURL(/progetti\/p1/);
  await page.getByRole("tab", { name: "Consuntivi", exact: true }).click();
  await page.getByRole("button", { name: /Consuntiva|Nuovo consuntivo/ }).click();
  await page.getByLabel("Giornate", { exact: true }).fill("1");
  await page.getByLabel("Data", { exact: true }).fill("2026-10-28");
  await page.getByLabel("Descrizione", { exact: true }).fill("Prova frontend");
  await page.getByRole("button", { name: "Salva", exact: true }).click();
  await expect.poll(() => writes.some((w) => w.path === "/projects/p1/ledger")).toBeTruthy();
  await expect(page.getByText("Prova frontend")).toBeVisible();
  await capture(page, "progetti-consuntivi");
});
test("wallet: drawer, tastiera, update e nuovo utilizzo", async ({ page }) => {
  const { writes } = await installFixtures(page);
  await page.goto("/wallet");
  const row = page.getByTestId("allocation-row-open");
  await row.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: "Allocazione wallet", exact: true })).toBeVisible();
  await capture(page, "wallet-drawer");
  await audit(page, "wallet-drawer");
  await page.keyboard.press("Escape");
  await expect(row).toBeFocused();
  await row.click();
  await expect(page.getByRole("dialog", { name: "Allocazione wallet", exact: true })).toBeVisible();
  await capture(page, "wallet-reopened");
  await page.getByLabel("Note", { exact: true }).fill("Nota aggiornata");
  await page.getByRole("button", { name: "Salva", exact: true }).click();
  await expect
    .poll(() => writes.some((w) => w.path === "/wallet/allocations/open" && w.method === "PATCH"))
    .toBeTruthy();
  await page.getByRole("button", { name: "Chiudi dettaglio" }).click();
  await page.getByRole("button", { name: "Nuovo utilizzo" }).click();
  await capture(page, "wallet-nuovo-dialog");
  await audit(page, "wallet-nuovo");
  await page.getByRole("button", { name: "+ Nuova attivit\u00e0", exact: true }).click();
  await page.getByPlaceholder("Nome attività").fill("Attivita nuova");
  await page.getByLabel("Assegnatario *", { exact: true }).selectOption("person1");
  await page.getByLabel("Giornate da riservare *", { exact: true }).fill("2");
  await page
    .getByRole("button", { name: /Crea|Registra/ })
    .last()
    .click();
  await expect.poll(() => writes.some((w) => w.path === "/allocations")).toBeTruthy();
});
test("organico: creazione attivita, modifica e consuntivo", async ({ page }) => {
  const { writes } = await installFixtures(page);
  await page.goto("/canone");
  await page.getByRole("button", { name: "Nuova attività", exact: true }).click();
  await page.getByLabel("Titolo attività", { exact: true }).fill("Attivita nuova");
  await page.getByLabel("Redmine", { exact: true }).fill("300999");
  await page.getByLabel("Gruppo architetturale").selectOption("EA");
  await page.getByLabel("Giornate da riservare").fill("2");
  await page.getByRole("button", { name: "Aggiungi attività" }).click();
  await expect.poll(() => writes.some((w) => w.path === "/canoni/one/subactivities")).toBeTruthy();
  await page.getByRole("button", { name: /Analisi architetturale/ }).click();
  await page.getByRole("button", { name: "Modifica attività", exact: true }).click();
  await page.getByLabel("Redmine in modifica").fill("300229");
  await page.getByRole("button", { name: "Salva modifiche", exact: true }).click();
  await expect
    .poll(() => writes.some((w) => w.path === "/canoni/one/subactivities/s1"))
    .toBeTruthy();
  await page.getByRole("tab", { name: "Consuntivi" }).click();
  await page.getByRole("button", { name: "Nuovo consuntivo" }).click();
  await page.getByLabel("Data consuntivo").fill("2026-10-28");
  await page.getByLabel("Giornate consuntivo").fill("1");
  await page.getByLabel("Descrizione consuntivo").fill("Prova");
  await capture(page, "organico-consuntivo");
  await page.getByRole("button", { name: "Registra", exact: true }).click();
  await expect.poll(() => writes.some((w) => w.path.endsWith("/timesheets"))).toBeTruthy();
});
test("controllo: date, Top N, riconciliazione, deroga e revisione", async ({ page }) => {
  const { writes } = await installFixtures(page);
  await page.goto("/analisi-costi");
  await page.getByLabel("Dal", { exact: true }).fill("2026-01-01");
  await page.getByLabel("Al", { exact: true }).fill("2026-12-31");
  const request = page.waitForRequest((r) => r.url().includes("cost-analysis?"));
  await page.getByRole("button", { name: "Applica filtri" }).click();
  expect((await request).url()).toContain("from=2026-01-01");
  await page.getByLabel("Cerca progetto").fill("inesistente");
  await expect(page.getByText("Nessun progetto corrisponde alla ricerca.")).toBeVisible();
  await page.goto("/riconciliazione");
  await page.getByLabel("Filtra esito riconciliazione").selectOption("KO");
  await expect(page.getByText("DISCREPANZA")).toBeVisible();
  await expect(page.getByText("Valido", { exact: true })).toHaveCount(0);
  await page.goto("/anomalie");
  await page.getByRole("button", { name: "Accetta con deroga" }).click();
  await page.getByLabel("Scadenza deroga").fill("2027-06-30");
  await capture(page, "anomalie-deroga");
  await page.getByRole("button", { name: "Conferma deroga" }).click();
  await expect.poll(() => writes.some((w) => w.path === "/anomalies/a1/accept")).toBeTruthy();
  await page.goto("/revisione");
  await page.getByRole("button", { name: "Conferma revisione" }).click();
  await page.getByLabel(/Data chiusura per/).fill("2026-10-28");
  await capture(page, "revisione-form");
  await page.getByRole("button", { name: "Salva", exact: true }).click();
  await expect
    .poll(() => writes.some((w) => w.path === "/projects/p1/confirm-review"))
    .toBeTruthy();
});
test("amministrazione: import, cambio file, utenti, ruoli e configurazione", async ({ page }) => {
  const { writes } = await installFixtures(page);
  await page.goto("/amministrazione");
  const file = page.getByLabel("File per Import JSON (seed v1 o workbook v2-v4)");
  const panel = file.locator("xpath=ancestor::section[1]");
  await file.setInputFiles({
    name: "seed.json",
    mimeType: "application/json",
    buffer: Buffer.from("{}"),
  });
  await panel.getByRole("button", { name: "Valida e simula" }).click();
  await expect(panel.getByRole("button", { name: "Conferma e applica" })).toBeEnabled();
  await file.setInputFiles({
    name: "altro.json",
    mimeType: "application/json",
    buffer: Buffer.from("{}"),
  });
  await expect(panel.getByRole("button", { name: "Conferma e applica" })).toBeDisabled();
  await panel.getByRole("button", { name: "Valida e simula" }).click();
  await audit(page, "admin-preview-enabled");
  await capture(page, "admin-preview-enabled");
  await panel.getByRole("button", { name: "Conferma e applica" }).click();
  await capture(page, "admin-import-result");
  await page.getByRole("tab", { name: "Utenti", exact: true }).click();
  await page.getByRole("button", { name: /Crea utente|Nuovo utente/ }).click();
  await capture(page, "admin-utente-dialog");
  await audit(page, "admin-utente");
  await page.getByLabel("Username", { exact: true }).fill("utente-test");
  await page.getByLabel("Password iniziale").fill("SoloFixture123!");
  await page.getByRole("button", { name: "Salva", exact: true }).click();
  await expect.poll(() => writes.some((w) => w.path === "/admin/users")).toBeTruthy();
  await page.getByRole("tab", { name: "Referenti", exact: true }).click();
  await expect(page.getByText("Mario Bianchi")).toBeVisible();
  await page.getByRole("tab", { name: "Ruoli e privilegi" }).click();
  await page.getByRole("button", { name: "Salva Fornitore" }).click();
  await expect.poll(() => writes.some((w) => w.path === "/admin/roles/capabilities")).toBeTruthy();
  await page.getByRole("tab", { name: "Configurazione", exact: true }).click();
  await page.getByLabel("Costo giornata uomo (€)").fill("450");
  await page.getByRole("button", { name: "Salva", exact: true }).click();
  await expect(page.getByText("Configurazione salvata.")).toBeVisible();
});
test("permessi consultivi e navigazione menu", async ({ page }) => {
  await installFixtures(page, "normal", true);
  await page.goto("/progetti");
  await expect(page.getByRole("button", { name: "Nuovo progetto" })).toHaveCount(0);
  await expect(page.getByTestId("edit-project-p1")).toHaveCount(0);
  await page.getByRole("button", { name: "Menu account" }).click();
  await expect(page.getByRole("menuitem", { name: "Esci" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Menu account" })).toBeFocused();
  await page.getByRole("button", { name: "Riduci il menu" }).click();
  await expect(page.getByRole("link", { name: "Wallet", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Wallet", exact: true }).click();
  await expect(page.getByRole("button", { name: "Nuovo utilizzo" })).toHaveCount(0);
});

test("errori di mutazione, retry e validazione revisione", async ({ page }) => {
  const { writes, unhandled } = await installFixtures(page);
  let fail = true;
  await page.route("**/api/v1/anomalies/a1/accept", (route) =>
    fail
      ? route.fulfill({
          status: 422,
          json: {
            status: 422,
            title: "Deroga non salvata",
            detail: "La scadenza richiede una verifica del responsabile",
          },
        })
      : route.fallback(),
  );
  await page.goto("/anomalie");
  await page.getByRole("button", { name: "Accetta con deroga" }).click();
  await expect(page.getByRole("button", { name: "Conferma deroga" })).toBeDisabled();
  await page.getByLabel("Scadenza deroga").fill("2027-06-30");
  await page.getByRole("button", { name: "Conferma deroga" }).click();
  await expect(page.getByRole("alert")).toHaveText(
    "La scadenza richiede una verifica del responsabile",
  );
  await capture(page, "anomalie-mutation-error");
  fail = false;
  await page.getByRole("button", { name: "Conferma deroga" }).click();
  await expect(page.getByRole("status")).toHaveText("Anomalia aggiornata.");
  await page.goto("/revisione");
  await page.getByRole("button", { name: "Conferma revisione" }).click();
  await page.getByLabel(/Data chiusura per/).fill("");
  await expect(page.getByRole("button", { name: "Salva", exact: true })).toBeEnabled();
  await page.getByLabel(/Stato per/).selectOption("CHIUSO");
  await expect(page.getByRole("button", { name: "Salva", exact: true })).toBeDisabled();
  await page.getByLabel(/Data chiusura per/).fill("2026-10-28");
  await page.getByRole("button", { name: "Salva", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Revisione confermata.");
  expect(writes.find((w) => w.path.endsWith("/confirm-review"))?.body).toMatchObject({
    timesheet_status: "CHIUSO",
    actual_closure_date: "2026-10-28",
  });
  await page.waitForLoadState("networkidle");
  expect(unhandled).toEqual([]);
});

test("errori parziali dashboard e movimenti progetto", async ({ page }) => {
  await installFixtures(page);
  await page.route("**/api/v1/wallet/*/balance", (route) =>
    route.fulfill({ status: 503, json: { status: 503, title: "Fonte wallet non disponibile" } }),
  );
  await page.goto("/");
  await expect(page.getByText("Errore caricamento").first()).toBeVisible();
  await expect(page.getByText("+2,00 gg")).toBeVisible();
  await capture(page, "dashboard-source-error");
  await page.route("**/api/v1/projects/p1/ledger", (route) =>
    route.fulfill({ status: 503, json: { status: 503, title: "Movimenti non disponibili" } }),
  );
  await page.goto("/progetti/p1");
  await page.getByRole("tab", { name: "Consuntivi", exact: true }).click();
  await expect(page.getByText("Impossibile caricare i movimenti del progetto")).toBeVisible();
  await expect(page.getByText("Nessun consuntivo registrato")).toHaveCount(0);
  await capture(page, "progetti-ledger-error");
});

test("organico: modifica canone e conferme sicure", async ({ page }) => {
  const { writes, unhandled } = await installFixtures(page);
  await page.goto("/canone");
  await page.getByRole("button", { name: "Modifica", exact: true }).click();
  await page.getByLabel("Nome canone", { exact: true }).fill("Organico verificato");
  await page.getByRole("button", { name: "Salva", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Organico verificato/ })).toBeVisible();
  const opener = page.getByRole("button", { name: "Elimina", exact: true });
  await opener.click();
  await expect(page.getByRole("dialog", { name: "Elimina canone" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Annulla", exact: true })).toBeFocused();
  await capture(page, "organico-conferma-eliminazione");
  await audit(page, "organico-conferma");
  await page.keyboard.press("Escape");
  await expect(opener).toBeFocused();
  expect(writes.filter((w) => w.method === "DELETE")).toHaveLength(0);
  await page.getByRole("button", { name: /Analisi architetturale/ }).click();
  await page.getByRole("button", { name: "ELIMINA", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Elimina attivit\u00e0" })).toBeVisible();
  await page.getByRole("button", { name: "Annulla", exact: true }).click();
  await page.getByRole("tab", { name: "Consuntivi", exact: true }).click();
  await page
    .getByRole("tabpanel", { name: "Consuntivi", exact: true })
    .getByRole("button", { name: "Modifica", exact: true })
    .click();
  await page.getByLabel("Giornate consuntivo").fill("24");
  await page.getByRole("button", { name: "Salva rettifica", exact: true }).click();
  await expect
    .poll(() => writes.some((w) => w.method === "PATCH" && w.path.endsWith("/timesheets/ts1")))
    .toBeTruthy();
  await page.waitForLoadState("networkidle");
  expect(unhandled).toEqual([]);
});

test("amministrazione: PPM, download e referenti", async ({ page }) => {
  const { writes, unhandled } = await installFixtures(page);
  await page.goto("/amministrazione");
  const file = page.getByLabel("File per Import PPM");
  const panel = file.locator("xpath=ancestor::section[1]");
  await file.setInputFiles({
    name: "ppm.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("codice,giornate\nTEST,1"),
  });
  await panel.getByRole("button", { name: "Valida e simula" }).click();
  await expect(panel.getByRole("button", { name: "Conferma e applica" })).toBeEnabled();
  await panel.getByRole("button", { name: "Conferma e applica" }).click();
  await expect.poll(() => writes.filter((w) => w.path === "/admin/imports/ppm").length).toBe(2);
  for (const name of ["JSON", "Excel", "Scarica backup database"]) {
    const download = page.waitForEvent("download");
    await page.getByRole("link", { name, exact: true }).click();
    expect((await download).suggestedFilename()).toMatch(/export-test|fixture/);
  }
  const restore = page.getByRole("button", { name: "Ripristina database", exact: true });
  await expect(restore).toBeDisabled();
  await page.getByLabel("File backup database").setInputFiles({
    name: "fixture.dump",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("fixture"),
  });
  await expect(restore).toBeDisabled();
  await page.getByLabel(/Scrivi RIPRISTINA/).fill("RIPRISTINA");
  await expect(restore).toBeEnabled();
  await page.getByLabel("File backup database").setInputFiles({
    name: "altro.dump",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("fixture"),
  });
  await expect(restore).toBeDisabled();
  expect(writes.some((w) => w.path.includes("/restore"))).toBeFalsy();
  await page.getByRole("tab", { name: "Referenti", exact: true }).click();
  await page.getByLabel("Nome e cognome", { exact: true }).fill("Referente di prova");
  await page.getByLabel("Email", { exact: true }).fill("referente@example.test");
  await page.getByRole("button", { name: "Aggiungi", exact: true }).click();
  await expect
    .poll(() => writes.some((w) => w.path === "/admin/referents" && w.method === "POST"))
    .toBeTruthy();
  await page.getByRole("button", { name: "Modifica", exact: true }).click();
  await page.getByLabel("Nome e cognome", { exact: true }).fill("Referente aggiornato");
  await page.getByRole("button", { name: "Aggiorna", exact: true }).click();
  await expect
    .poll(() => writes.some((w) => w.path === "/admin/referents/ref1" && w.method === "PATCH"))
    .toBeTruthy();
  await page.waitForLoadState("networkidle");
  expect(unhandled).toEqual([]);
});

test("dialog, drawer, tab e tooltip a 1024 nei due temi", async ({ page }) => {
  test.setTimeout(120000);
  const { writes, unhandled } = await installFixtures(page);
  await page.setViewportSize({ width: 1024, height: 768 });
  for (const theme of ["dark", "light"]) {
    await page.goto("/progetti");
    await page.locator("main h1").waitFor();
    if ((await page.locator("html").getAttribute("data-theme")) !== theme)
      await page
        .getByRole("button", {
          name: theme === "light" ? "Tema chiaro" : "Tema scuro",
          exact: true,
        })
        .click();
    await page.getByTestId("edit-project-p1").click();
    await page.getByRole("dialog").getByLabel("Titolo", { exact: true }).waitFor();
    await audit(page, `progetti-edit-${theme}-1024`);
    await capture(page, `progetti-edit-${theme}-1024`);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("edit-project-p1")).toBeFocused();
    await page.goto("/wallet");
    await page.getByTestId("allocation-row-open").click();
    await page.getByLabel("Note", { exact: true }).waitFor();
    await audit(page, `wallet-drawer-${theme}-1024`);
    await capture(page, `wallet-drawer-${theme}-1024`);
    await page.getByLabel("Note", { exact: true }).focus();
    await capture(page, `wallet-drawer-${theme}-1024-bottom`);
    await page.keyboard.press("Escape");
    await page.goto("/amministrazione");
    await page.getByRole("tab", { name: "Import ed export" }).focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: "Utenti", exact: true })).toBeFocused();
    await expect(page.getByRole("tab", { name: "Utenti", exact: true })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    for (const tab of ["Utenti", "Referenti", "Ruoli e privilegi", "Configurazione"]) {
      await page.getByRole("tab", { name: tab, exact: true }).click();
      await page.waitForLoadState("networkidle");
      await audit(page, `admin-${tab}-${theme}-1024`);
      await capture(page, `admin-${tab}-${theme}-1024`);
    }
    await page.getByTestId("open-delete-db-dialog-btn").click();
    await page.getByRole("button", { name: "Conferma eliminazione DB" }).waitFor();
    await expect(page.getByRole("button", { name: "Conferma eliminazione DB" })).toBeDisabled();
    await audit(page, `admin-reset-${theme}`);
    await capture(page, `admin-reset-${theme}`);
    await page.keyboard.press("Escape");
  }
  expect(writes.filter((w) => w.path === "/admin/reset-data")).toEqual([]);
  expect(unhandled).toEqual([]);
  await page.goto("/");
  const tooltip = page
    .getByRole("button", {
      name: "Informazioni su Wallet disponibile",
      exact: true,
    })
    .first();
  await tooltip.focus();
  await expect(page.getByRole("tooltip")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("dialog")).toBeVisible();
  await audit(page, "ricerca-globale");
  await capture(page, "ricerca-globale");
  await page.getByRole("combobox").fill("portale");
  await page.getByRole("option", { name: /IM26001/ }).click();
  await expect(page).toHaveURL(/progetti\/p1/);
});

test("tabella popolata, scroll locale, filtri e Top N indipendenti", async ({ page }) => {
  await installFixtures(page);
  const response = page.waitForResponse((r) => r.url().endsWith("/projects/balances"));
  await page.goto("/progetti");
  const data = await (await response).json();
  const results = Array.from({ length: 24 }, (_, i) => ({
    ...data.results[0],
    id: `stress${i}`,
    codice: `LONG-CODE-${i}-ARCHITETTURA`,
    titolo: `${i.toString().padStart(2, "0")} - Progetto con un titolo esteso per verificare allineamenti e leggibilita della tabella`,
    budget: String(i * 10),
    consumato_totale: String(i),
    residuo: String(i * 9),
  }));
  await page.route("**/api/v1/projects/balances", (r) =>
    r.fulfill({ json: { count: 24, results } }),
  );
  await page.reload();
  await expect(page.getByText("24 risultati")).toBeVisible();
  await page.setViewportSize({ width: 1024, height: 768 });
  const region = page.getByRole("region", { name: "Tabella dati" });
  await region.evaluate((e) => {
    e.scrollTop = e.scrollHeight;
    e.scrollLeft = e.scrollWidth;
  });
  await page.getByTestId("edit-project-stress23").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("edit-project-stress23")).toBeInViewport();
  await capture(page, "progetti-stress-scroll");
  expect(
    await page.evaluate<boolean>("document.documentElement.scrollWidth<=innerWidth"),
  ).toBeTruthy();
  await page.getByLabel("Ordina progetti").selectOption("code");
  await page.getByLabel("Filtra stato operativo").selectOption("IN_CORSO");
  await page.getByRole("button", { name: "Azzera filtri" }).click();
  await page.setViewportSize({ width: 1440, height: 900 });
  const costResponse = page.waitForResponse((r) => r.url().endsWith("/cost-analysis"));
  await page.goto("/analisi-costi");
  const costs = await (await costResponse).json();
  const by_project = Array.from({ length: 12 }, (_, i) => ({
    label: `Progetto ${i + 1}`,
    days: String(12 - i),
    cost: String((12 - i) * 400),
  }));
  await page.route("**/api/v1/cost-analysis", (r) => r.fulfill({ json: { ...costs, by_project } }));
  await page.reload();
  const table = page.getByRole("table", { name: "Riepilogo accessibile dei costi per progetto" });
  await expect(table.locator("tbody tr")).toHaveCount(10);
  await page.getByLabel("Numero di progetti").selectOption("5");
  await expect(table.locator("tbody tr")).toHaveCount(5);
  await expect(
    page
      .getByRole("article")
      .filter({ has: page.getByText("Costo totale", { exact: true }) })
      .getByText("10.000,00 €", { exact: true }),
  ).toBeVisible();
  await capture(page, "costi-top5");
  await page.getByLabel("Cerca progetto").fill("Progetto 12");
  await expect(table.locator("tbody tr")).toHaveCount(1);
  await expect(
    page
      .getByRole("article")
      .filter({ has: page.getByText("Costo totale", { exact: true }) })
      .getByText("10.000,00 €", { exact: true }),
  ).toBeVisible();
});

test("diagnostica scroll e viewport", async ({ page }) => {
  await installFixtures(page);
  await page.goto("/canone");
  await page.waitForLoadState("networkidle");
  const data = await page.evaluate(
    "Array.from(document.querySelectorAll('html,body,#root,main,aside')).map(e=>({tag:e.tagName,id:e.id,height:e.clientHeight,scroll:e.scrollHeight,top:e.getBoundingClientRect().top,css:getComputedStyle(e).overflow}))",
  );
  await fs.writeFile(`${folder}/scroll-diagnostics.json`, JSON.stringify(data, null, 2));
  await page.screenshot({ path: `${folder}/organico-entire-page.png`, fullPage: true });
});

test("cambio canone senza dati precedenti, retry e aggregazioni parziali", async ({ page }) => {
  const { unhandled } = await installFixtures(page);
  const listResponse = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/v1/canoni");
  const detailResponse = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/v1/canoni/one",
  );
  await page.goto("/canone");
  const list = await (await listResponse).json();
  const detail = await (await detailResponse).json();
  const next = { ...list.results[0], id: "two", nome: "Canone successivo", semestre: "2027-S1" };
  await page.route("**/api/v1/canoni?*", (r) =>
    r.fulfill({ json: { ...list, count: 2, results: [...list.results, next] } }),
  );
  let release: () => void = () => {};
  const delayed = new Promise<void>((resolve) => {
    release = resolve;
  });
  let fail = true;
  await page.route("**/api/v1/canoni/two*", async (route) => {
    await delayed;
    return fail
      ? route.fulfill({ status: 503, json: { status: 503, title: "Dettaglio non disponibile" } })
      : route.fulfill({
          json: {
            ...detail,
            id: "two",
            name: "Canone successivo",
            semester: "2027-S1",
            start_date: "2027-01-01",
            end_date: "2027-06-30",
            subactivities: [
              { ...detail.subactivities[0], id: "s2", title: "Attivita del nuovo canone" },
            ],
          },
        });
  });
  await page.reload();
  await page.getByRole("cell", { name: "Canone successivo", exact: true }).click();
  await expect(page.getByRole("status", { name: "Caricamento", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Analisi architetturale/ })).toHaveCount(0);
  release();
  await expect(page.getByText("Impossibile caricare il canone", { exact: true })).toBeVisible();
  await page.getByText("Impossibile caricare il canone", { exact: true }).scrollIntoViewIfNeeded();
  await capture(page, "organico-detail-error");
  fail = false;
  await page.getByRole("button", { name: "Riprova", exact: true }).click();
  await expect(page.getByRole("button", { name: /Attivita del nuovo canone/ })).toBeVisible();
  await page.getByRole("button", { name: /Attivita del nuovo canone/ }).scrollIntoViewIfNeeded();
  await capture(page, "organico-cambio-selezione");
  await audit(page, "organico-cambio-selezione");
  const costResponse = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/v1/cost-analysis",
  );
  await page.goto("/analisi-costi");
  const costs = await (await costResponse).json();
  await page.route("**/api/v1/cost-analysis", (r) =>
    r.fulfill({ json: { ...costs, by_supplier: [] } }),
  );
  await page.reload();
  await expect(page.getByText("Nessun dato per questa aggregazione.")).toBeVisible();
  await page.getByText("Nessun dato per questa aggregazione.").scrollIntoViewIfNeeded();
  await capture(page, "costi-aggregazione-vuota");
  await page.waitForLoadState("networkidle");
  expect(unhandled).toEqual([]);
});
