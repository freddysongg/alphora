import { test, expect } from "@playwright/test";

/**
 * Manual smoke test for the macro run detail flow. This config does NOT
 * auto-start the dev server. Bring up the app on `BASE_URL` (default
 * `http://localhost:3000`) and point it at an API with at least one
 * funnel_research run, then run `pnpm e2e:smoke`.
 *
 * Set `MACRO_RUN_ID` in the environment to point at a known run id, or the
 * test will skip itself when not provided.
 */

const macroRunId = process.env.MACRO_RUN_ID;

test.describe("macro run detail", () => {
  test.skip(
    macroRunId === undefined,
    "MACRO_RUN_ID env var required for this smoke",
  );

  test("renders macro brief, judge badge, and at least one sector card", async ({
    page,
  }) => {
    await page.goto(`/research/runs/${macroRunId}`);
    await expect(page.getByRole("heading", { name: /macro brief/i })).toBeVisible();
    await expect(page.getByTestId("judge-badge")).toBeVisible();
    const sectorCards = page.getByTestId("sector-brief-card");
    await expect(sectorCards.first()).toBeVisible();
  });
});
