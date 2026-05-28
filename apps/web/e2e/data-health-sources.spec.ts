import { test, expect } from "@playwright/test";

test("data health sources page renders and pulls", async ({ page }) => {
  await page.goto("/data-health/sources");
  await expect(page.getByRole("heading", { name: /data health/i })).toBeVisible();

  const tickerInput = page.getByLabel(/ticker/i);
  await tickerInput.fill("AAPL");

  await page.getByRole("button", { name: /^pull all$/i }).click();

  await expect(page.getByText(/enabled/i).first()).toBeVisible();
});
