import { expect, test } from "@playwright/test";

import { installFixtures } from "./fixtures";

/**
 * Regressione: `main` e l'unico scroller dell'applicazione.
 *
 * Gli elementi in `position: absolute` dentro i contenuti (le etichette `.sr-only`, per
 * esempio) si ancorano al primo antenato posizionato: se `main` non lo e, si riferiscono al
 * viewport, sfuggono al suo `overflow: auto` e allungano il documento. Nasce cosi una
 * seconda barra di scorrimento, e scorrendola l'utente si porta via header e sidebar
 * lasciando una fascia vuota sotto la pagina.
 */
function subactivities(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    id: `s${index}`,
    version: 1,
    office: ["TA", "EA", "SA", "CROSS"][index % 4],
    title: `Attivita numero ${index}`,
    reserved_days: "22.0000",
    start_date: "2026-07-01",
    end_date: "2026-12-31",
    remaining_reserved_days: "14.5600",
    redmine_ref: `26018${index}`,
    quarter_estimate_days: null,
    forecast_remaining_days: null,
    notes: "",
    needs_review: false,
    consuntivato: "7.4400",
    stato: "IN_CORSO",
    timesheet_count: 0,
    consuntivi: [],
  }));
}

test("la finestra non scorre: scorre solo il contenuto", async ({ page }) => {
  await installFixtures(page);
  // Un canone con molte attivita: serve un contenuto piu alto del viewport.
  await page.route("**/api/v1/canoni/one*", (route) =>
    route.fulfill({
      json: {
        id: "one",
        version: 1,
        name: "Organico Allargato",
        semester: "2026-S2",
        periodicity: "SEMESTRALE",
        total_days: "173",
        reserved_days: "173",
        available_days: "0",
        target_base_days: "0",
        target_days_per_week: "0",
        cap_at_total: true,
        start_date: "2026-07-01",
        end_date: "2026-12-31",
        status: {
          consuntivato: "25",
          target_alla_data: "0",
          delta: "-25",
          forecast: "50",
          percentuale_forecast: "50",
          proiezione: "Sotto-utilizzo previsto",
          giornate_non_usate_previste: "50",
        },
        subactivities: subactivities(30),
      },
    }),
  );

  await page.goto("/canone");
  const activity = page.getByRole("button", { name: /Attivita numero 25/ });
  await activity.waitFor();

  const geometry = () =>
    page.evaluate(() => ({
      documentScrollHeight: document.scrollingElement?.scrollHeight ?? 0,
      viewportHeight: window.innerHeight,
      windowScrollY: window.scrollY,
      contentScrollHeight: document.querySelector("main")?.scrollHeight ?? 0,
    }));

  const initial = await geometry();
  // Il contenuto e piu alto del viewport, ma il documento no.
  expect(initial.contentScrollHeight).toBeGreaterThan(initial.viewportHeight);
  expect(initial.documentScrollHeight).toBe(initial.viewportHeight);

  // Scorrere fino in fondo, poi aprire un'attivita, non deve muovere la finestra.
  await page.evaluate(() => {
    const main = document.querySelector("main");
    if (main) main.scrollTop = main.scrollHeight;
    window.scrollTo(0, document.body.scrollHeight);
  });
  expect((await geometry()).windowScrollY).toBe(0);

  await activity.click();
  await page.getByRole("button", { name: "← Tutte le attività" }).waitFor();
  const afterSelection = await geometry();
  expect(afterSelection.windowScrollY).toBe(0);
  expect(afterSelection.documentScrollHeight).toBe(afterSelection.viewportHeight);
  // Header e sidebar restano al loro posto.
  await expect(page.getByRole("button", { name: /Riduci|Espandi il menu/ })).toBeInViewport();
});
