import { expect, test } from "@playwright/test";

const E2E_USER = process.env.E2E_USERNAME;
const E2E_PASS = process.env.E2E_PASSWORD;

if (!E2E_USER || !E2E_PASS) {
  throw new Error("Impostare E2E_USERNAME ed E2E_PASSWORD per eseguire i test browser.");
}

test("login reale e navigazione verso anomalie e riconciliazione", async ({ page }) => {
  await page.goto("/");
  await page.locator("#username").fill(E2E_USER);
  await page.locator("#password").fill(E2E_PASS);
  await page.getByRole("button", { name: "Accedi" }).click();

  await expect(page.getByRole("button", { name: "Esci" })).toBeVisible({ timeout: 10000 });

  await page.goto("/anomalie");
  await expect(page.getByRole("heading", { name: "Inbox anomalie" })).toBeVisible();
  await expect(page.getByText("CHK_OVERRUN_PROJECT").first()).toBeVisible();

  await page.goto("/riconciliazione");
  await expect(page.getByRole("heading", { name: "Riconciliazione PPM" })).toBeVisible();
  await expect(page.getByText("IM24133").first()).toBeVisible();
});
