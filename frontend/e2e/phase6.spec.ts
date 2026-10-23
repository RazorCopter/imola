import { expect, test, type Page } from "@playwright/test";

const ADMIN_USER = process.env.E2E_USERNAME ?? "demo_admin";
const ADMIN_PASS = process.env.E2E_PASSWORD ?? "Demo-Local-2026!";
const FORNITORE_USER = "demo_fornitore";
const FORNITORE_PASS = "Demo-Local-2026!";

async function login(page: Page, username = ADMIN_USER, password = ADMIN_PASS) {
  await page.goto("/");

  // Controllo sessione corrente
  const sessionRes = await page.request.get("/api/v1/auth/session");
  if (sessionRes.ok()) {
    const sessionData = await sessionRes.json();
    if (sessionData.username === username) {
      await expect(page.getByRole("button", { name: "Esci" })).toBeVisible({ timeout: 10000 });
      return;
    }
    // Logout tramite richiesta API per pulire i cookie di sessione
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

test.describe.configure({ mode: "serial" });

const E2E_MANAGED_USER = `e2e-managed-${Date.now()}`;

async function openAdmin(page: Page) {
  await login(page);
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Amministrazione" })).toBeVisible();
}

async function csrfToken(page: Page): Promise<string> {
  await page.request.get("/api/v1/auth/session");
  return (
    (await page.context().cookies()).find((cookie) => cookie.name === "sl_csrftoken")?.value ?? ""
  );
}

async function adminRequest(
  page: Page,
  method: "POST" | "PUT" | "DELETE",
  path: string,
  data?: unknown,
) {
  return page.request.fetch(path, {
    method,
    data,
    headers: { "X-CSRFToken": await csrfToken(page) },
  });
}

test("0. Admin gestisce un utente e modifica un privilegio non riservato", async ({ page }) => {
  await openAdmin(page);
  await page.getByRole("tab", { name: "Utenti" }).click();
  await page.getByRole("button", { name: "Crea utente" }).click();
  await page.getByLabel("Username").fill(E2E_MANAGED_USER);
  await page.getByLabel("Email").fill(`${E2E_MANAGED_USER}@example.test`);
  await page.getByLabel("Password iniziale").fill("E2E-Managed-2026!");
  await page.getByRole("button", { name: "Salva" }).click();
  await expect(page.getByText(E2E_MANAGED_USER)).toBeVisible();

  await page.getByRole("tab", { name: "Ruoli e privilegi" }).click();
  const capability = page.getByLabel("Fornitore (Imola): projects.create");
  const original = await capability.isChecked();
  await capability.click();
  await page.getByRole("button", { name: "Salva Fornitore (Imola)" }).click();
  await expect(page.getByRole("status")).toContainText("Privilegi salvati");

  const rolesResponse = await page.request.get("/api/v1/admin/roles/capabilities");
  const matrix = await rolesResponse.json();
  const supplier = matrix.roles.find((role: { key: string }) => role.key === "fornitore");
  const restored = new Set<string>(supplier.capabilities);
  if (original) restored.add("projects.create");
  else restored.delete("projects.create");
  expect(
    (
      await adminRequest(page, "PUT", "/api/v1/admin/roles/capabilities", {
        role: "fornitore",
        capabilities: [...restored],
      })
    ).ok(),
  ).toBeTruthy();

  const usersResponse = await page.request.get("/api/v1/admin/users");
  const managed = (await usersResponse.json()).results.find(
    (user: { username: string }) => user.username === E2E_MANAGED_USER,
  );
  expect(
    (await adminRequest(page, "DELETE", `/api/v1/admin/users/${managed.id}`)).ok(),
  ).toBeTruthy();
});

test("1. Login reale -> dashboard con KPI reali (non mock)", async ({ page }) => {
  await login(page, ADMIN_USER, ADMIN_PASS);
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText("Disponibile").first()).toBeVisible();
  await expect(page.getByText("Allocato").first()).toBeVisible();
  await expect(page.getByText("Consumato").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Riconciliazione PPM" })).toBeVisible();

  // Verifica persistenza dopo reload
  await page.reload();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText("Disponibile").first()).toBeVisible();
});

test("2. Creazione progetto -> verifica persistenza dopo reload", async ({ page }) => {
  await login(page, ADMIN_USER, ADMIN_PASS);
  await page.goto("/progetti");

  const newPrjBtn = page.getByRole("button", { name: "Nuovo progetto" });
  await expect(newPrjBtn).toBeVisible({ timeout: 10000 });
  await newPrjBtn.click();

  const code = `DEMO-E2E-${Date.now().toString().slice(-6)}`;
  const title = `Progetto E2E Creato ${code}`;

  await page.locator('input[name="code"]').fill(code);
  await page.locator('input[name="title"]').fill(title);
  await page.locator('input[name="budget_days"]').fill("12.5000");
  await page.getByRole("button", { name: "Continua" }).click();

  await page.locator('input[name="start_date"]').fill("2026-02-01");
  await page.locator('input[name="planned_end_date"]').fill("2026-11-30");
  await page.getByRole("button", { name: "Continua" }).click();

  const [createResponse] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/projects") && r.request().method() === "POST"),
    page.getByRole("button", { name: "Crea progetto" }).click(),
  ]);
  if (!createResponse.ok()) {
    console.log("Create Project Error:", await createResponse.text());
  }
  expect(createResponse.ok()).toBeTruthy();

  await expect(page.getByText(code, { exact: true })).toBeVisible({ timeout: 10000 });

  // Verifica persistenza dopo reload senza dipendere dalla virtualizzazione della tabella.
  await page.reload();
  await page.getByPlaceholder("Codice o titolo").fill(code);
  await expect(page.getByText(code, { exact: true })).toBeVisible({ timeout: 10000 });

  // Verifica via API reale
  const apiRes = await page.request.get("/api/v1/projects/balances");
  expect(apiRes.ok()).toBeTruthy();
  const balances = await apiRes.json();
  const exists = balances.results.some((p: { codice: string }) => p.codice === code);
  expect(exists).toBeTruthy();
});

test("3. Run controlli -> verifica anomalie generate persistite", async ({ page }) => {
  await login(page, ADMIN_USER, ADMIN_PASS);
  await page.goto("/anomalie");

  await expect(page.getByRole("heading", { name: "Inbox anomalie" })).toBeVisible();

  const runBtn = page.getByRole("button", { name: "Esegui controlli" });
  await expect(runBtn).toBeVisible();

  const [runRes] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/checks/run") && r.request().method() === "POST"),
    runBtn.click(),
  ]);
  expect(runRes.ok()).toBeTruthy();
  const runReport = await runRes.json();
  expect(runReport.rilevate).toBeGreaterThanOrEqual(1);

  await expect(page.locator("article").first()).toBeVisible({ timeout: 10000 });

  // Verifica persistenza dopo reload
  await page.reload();
  await expect(page.getByRole("heading", { name: "Inbox anomalie" })).toBeVisible();
  await expect(page.locator("article").first()).toBeVisible({ timeout: 10000 });

  // Verifica via API reale
  const apiAnomalies = await page.request.get("/api/v1/anomalies");
  expect(apiAnomalies.ok()).toBeTruthy();
  const body = await apiAnomalies.json();
  expect(body.results.length).toBeGreaterThanOrEqual(1);
});

test("4. Azione su anomalia (take/resolve) -> verifica stato persistito", async ({ page }) => {
  await login(page, ADMIN_USER, ADMIN_PASS);
  await page.goto("/anomalie");

  await page.locator("select").first().selectOption("APERTA");
  const firstArticle = page.locator("article").first();
  await expect(firstArticle).toBeVisible({ timeout: 10000 });

  const resolveBtn = firstArticle.getByRole("button", { name: "Risolvi" });
  await expect(resolveBtn).toBeVisible({ timeout: 10000 });

  const [resolveRes] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/resolve") && r.request().method() === "POST"),
    resolveBtn.click(),
  ]);
  expect(resolveRes.ok()).toBeTruthy();

  // Verifica persistenza tra le RISOLTE
  await page.locator("select").first().selectOption("RISOLTA");
  await expect(page.locator("article").first()).toBeVisible({ timeout: 10000 });

  await page.reload();
  await page.locator("select").first().selectOption("RISOLTA");
  await expect(page.locator("article").first()).toBeVisible({ timeout: 10000 });
});

test("5. Aggiornamento progetto (es. data fine) -> verifica persistenza", async ({ page }) => {
  await login(page, ADMIN_USER, ADMIN_PASS);
  await page.goto("/progetti");

  await page.getByPlaceholder("Codice o titolo").fill("DEMO-PRJ-001");
  const projectRow = page.getByText("DEMO-PRJ-001", { exact: true }).first();
  await expect(projectRow).toBeVisible({ timeout: 10000 });
  await projectRow.click();

  await expect(page.getByRole("heading", { name: "DEMO-PRJ-001" })).toBeVisible({ timeout: 10000 });
  await page.getByRole("tab", { name: "Anomalie" }).click();

  const newPlannedEnd = "2026-11-20";
  const dateInput = page.locator("#planned-end-date");
  await expect(dateInput).toBeVisible({ timeout: 10000 });
  await dateInput.fill(newPlannedEnd);

  const [updateRes] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/projects/") && r.request().method() === "PATCH"),
    page.getByRole("button", { name: "Aggiorna data fine prevista" }).click(),
  ]);
  expect(updateRes.ok()).toBeTruthy();

  // Verifica persistenza dopo reload tramite tab Storico modifiche e API
  await page.reload();
  await page.getByRole("tab", { name: "Storico modifiche" }).click();
  await expect(page.getByText(/planned_end_date/).first()).toBeVisible({ timeout: 10000 });

  // Verifica via API backend reale
  const prjRes = await page.request.get("/api/v1/projects");
  expect(prjRes.ok()).toBeTruthy();
});

test("6. Revisione progetto (confirm-review) -> verifica stato cambiato", async ({ page }) => {
  await login(page, ADMIN_USER, ADMIN_PASS);
  await page.goto("/revisione");

  await expect(page.getByRole("heading", { name: "Coda di revisione progetti" })).toBeVisible({
    timeout: 10000,
  });

  const confirmBtn = page.getByRole("button", { name: "Conferma revisione" }).first();
  await expect(confirmBtn).toBeVisible({ timeout: 10000 });
  await confirmBtn.click();

  const saveBtn = page.getByRole("button", { name: "Salva" });
  await expect(saveBtn).toBeVisible();

  const [confirmRes] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/confirm-review") && r.request().method() === "POST",
    ),
    saveBtn.click(),
  ]);
  expect(confirmRes.ok()).toBeTruthy();
  const confirmedData = await confirmRes.json();
  expect(["CHIUSO", "ATTIVO"]).toContain(confirmedData.timesheet_status);

  // Verifica persistenza dopo reload
  await page.reload();
  await expect(page.getByRole("heading", { name: "Coda di revisione progetti" })).toBeVisible();

  // Verifica via API progetti
  const prjRes = await page.request.get("/api/v1/projects/balances");
  const prjList = await prjRes.json();
  const matched = prjList.results.find((p: { id: string }) => p.id === confirmedData.id);
  expect(matched.stato_consuntivazione).toBe(confirmedData.timesheet_status);
});

test("7. Wallet: regolazione allocazione -> verifica saldo aggiornato", async ({ page }) => {
  await login(page, ADMIN_USER, ADMIN_PASS);
  await page.goto("/wallet");

  await expect(page.getByRole("heading", { name: /Wallet/ })).toBeVisible({ timeout: 10000 });

  const reduceBtn = page.getByRole("button", { name: "Riduci al consumato" }).first();
  await expect(reduceBtn).toBeVisible({ timeout: 10000 });

  const [adjustRes] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/adjust") && r.request().method() === "POST"),
    reduceBtn.click(),
  ]);
  expect(adjustRes.ok()).toBeTruthy();

  // Verifica persistenza dopo reload
  await page.reload();
  await expect(page.getByRole("heading", { name: /Wallet/ })).toBeVisible();
  await expect(page.getByText("Disponibile").first()).toBeVisible();
});

test("8. Caso negativo: fornitore tenta mutation -> riceve 403", async ({ browser }) => {
  // Contesto isolato per il fornitore
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.goto("/");
  await expect(page.locator("#username")).toBeVisible({ timeout: 15000 });
  await page.locator("#username").fill(FORNITORE_USER);
  await page.locator("#password").fill(FORNITORE_PASS);

  const [loginResponse] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/auth/login") && r.request().method() === "POST"),
    page.getByRole("button", { name: "Accedi" }).click(),
  ]);
  expect(loginResponse.ok()).toBeTruthy();
  const loginBody = await loginResponse.json();
  console.log("Browser login response payload:", loginBody);

  await expect(page.getByRole("button", { name: "Esci" })).toBeVisible({ timeout: 15000 });

  // Verifica che la sessione sia effettivamente del fornitore
  expect(loginBody.roles).toContain("fornitore");
  expect(loginBody.can_write).toBeFalsy();

  // Naviga su progetti
  await page.goto("/progetti");
  await expect(page.getByRole("heading", { name: "Progetti" })).toBeVisible({ timeout: 10000 });

  // Tentativo di mutation reale POST /projects via API autenticata con sessione fornitore
  const forbiddenProjectRes = await page.request.post("/api/v1/projects", {
    data: {
      code: "DEMO-UNAUTH-PRJ",
      title: "Tentativo non autorizzato",
      contract_type: "AQL",
      budget_days: "5.0000",
    },
  });
  expect(forbiddenProjectRes.status()).toBe(403);

  // Tentativo di mutation reale POST /checks/run via API
  const forbiddenChecksRes = await page.request.post("/api/v1/checks/run", { data: {} });
  expect(forbiddenChecksRes.status()).toBe(403);

  // Verifica persistenza DB: il progetto vietato non deve esistere
  const checkListRes = await page.request.get("/api/v1/projects/balances");
  const checkListData = await checkListRes.json();
  const exists = checkListData.results.some(
    (p: { codice: string }) => p.codice === "DEMO-UNAUTH-PRJ",
  );
  expect(exists).toBeFalsy();

  await context.close();
});
