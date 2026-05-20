import { test, expect } from "@playwright/test";

/**
 * Manual smoke for the per-run observability page. Like the macro-run-detail
 * spec, this does not auto-start the dev server. Bring up the app on `BASE_URL`
 * (default `http://localhost:3000`) and point it at an API with a real
 * funnel_research run, then set `MACRO_RUN_ID` and run `pnpm e2e:smoke`.
 */

const runId = process.env.MACRO_RUN_ID;

test.describe("run observability page", () => {
  test.skip(
    runId === undefined,
    "MACRO_RUN_ID env var required for this smoke",
  );

  test("renders all seven observability panels without console errors", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") {
        consoleErrors.push(message.text());
      }
    });
    await page.goto(`/research/runs/${runId}/observability`);
    await expect(page.getByTestId("observability-page")).toBeVisible();
    await expect(page.getByText("RUN TIMELINE")).toBeVisible();
    await expect(page.getByText("COST LEDGER")).toBeVisible();
    await expect(page.getByText("EVIDENCE FLOW")).toBeVisible();
    await expect(page.getByText("COUNTERFACTUAL MATRIX")).toBeVisible();
    await expect(page.getByText("LEAKAGE DECAY")).toBeVisible();
    await expect(page.getByText("INLINE CLAIM REVIEW")).toBeVisible();
    await expect(page.getByText("KNOWLEDGE GRAPH")).toBeVisible();
    expect(consoleErrors).toHaveLength(0);
  });
});
