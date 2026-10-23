import { expect, test } from "@playwright/test";

const wallet = {
  anno: 2026,
  allocato: "130.8900",
  consumato: "120.7900",
  disponibile: "10.1000",
  disponibile_da_allocazioni: "10.1000",
  disponibile_da_allocazioni_aperte: "10.1000",
  capienza_wallet_potenziale: "80.0150",
  residui_validi_non_allocati: "10.0000",
  residui_in_scadenza: "0.0000",
  budget_residuo_progetti_in_corso: "60.9150",
  sforamenti_progetti_in_corso: "-8.2400",
  residui_scaduti: "0.0000",
  residui_potenziali_da_verificare: "42.5400",
  dettaglio_residui: {},
};

async function authenticatedPage(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/auth/session", (route) =>
    route.fulfill({
      json: {
        authenticated: true,
        user: { username: "tester", full_name: "Test User", roles: ["responsabile_bmed"] },
      },
    }),
  );
  await page.route("**/api/v1/wallet/2026/balance", (route) => route.fulfill({ json: wallet }));
  await page.route("**/api/v1/reconciliation/latest", (route) =>
    route.fulfill({
      json: {
        riepilogo: {
          righe: 40,
          ok: 30,
          ko: 9,
          assenti_in_ppm: 1,
          delta_totale: "-8.2375",
          percentuale_allineati: "75.0000",
          snapshot_estratto_il: "2026-10-16T11:05:18+02:00",
        },
      },
    }),
  );
  await page.route("**/api/v1/projects/balances", (route) =>
    route.fulfill({
      json: {
        count: 1,
        results: [
          {
            id: "11111111-1111-1111-1111-111111111111",
            codice: "IM26254",
            titolo: "Progetto seed",
            tipo_contratto: "AQL",
            budget: "20.0000",
            consuntivi_diretti: "10.0000",
            allocato_a_wallet: "0.0000",
            consumato_via_wallet: "0.0000",
            consumato_totale: "10.0000",
            residuo: "10.0000",
            stato_consuntivazione: "ATTIVO",
            stato_fatturazione: "DA_FATTURARE",
            stato_offerta: "ACCETTATA",
            stato_residuo: "INFORMATIVO",
            residuo_scade_il: null,
            residuo_giorni_alla_scadenza: null,
            residuo_motivo: "Progetto attivo",
            spiegazione_residuo: "20 - 10 - 0 = 10",
          },
        ],
      },
    }),
  );
  await page.route("**/api/v1/wallet/2026/flow", (route) =>
    route.fulfill({ json: { results: [] } }),
  );
  await page.route("**/api/v1/canoni", (route) =>
    route.fulfill({ json: { results: [], count: 0 } }),
  );
  await page.route("**/api/v1/audit/**", (route) =>
    route.fulfill({ json: { results: [] } }),
  );
}

test("dashboard espone KPI API senza ricalcolarli", async ({ page }) => {
  await authenticatedPage(page);
  await page.goto("/");
  await expect(page.getByText("10,10 gg").first()).toBeVisible();
  await expect(page.getByText("60,92 gg").first()).toBeVisible();
  await expect(page.getByText("Cosa fare ora")).toBeVisible();
});

test("lista e dettaglio progetto distinguono gli stati", async ({ page }) => {
  await authenticatedPage(page);
  await page.goto("/progetti");
  await expect(page.getByText("IM26254")).toBeVisible();
  await page.getByText("IM26254").click();
  await expect(page.getByText("Consuntivazione:")).toBeAttached();
  await expect(page.getByText("Fatturazione:")).toBeAttached();
  await expect(page.getByText("Offerta:")).toBeAttached();
});
