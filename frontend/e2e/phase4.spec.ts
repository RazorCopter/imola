import { expect, test } from "@playwright/test";

test("login reale e navigazione verso anomalie e riconciliazione", async ({ page }) => {
  await page.goto("/");
  await page.locator("#username").fill("admin");
  await page.locator("#password").fill("admin1234");
  await page.getByRole("button", { name: "Accedi" }).click();

  await expect(page.getByRole("button", { name: "Esci" })).toBeVisible({ timeout: 10000 });

  await page.goto("/anomalie");
  await expect(page.getByRole("heading", { name: "Inbox anomalie" })).toBeVisible();
  await expect(page.getByText("CHK_OVERRUN_PROJECT").first()).toBeVisible();

  await page.goto("/riconciliazione");
  await expect(page.getByRole("heading", { name: "Riconciliazione PPM" })).toBeVisible();
  await expect(page.getByText("IM24133").first()).toBeVisible();
});
