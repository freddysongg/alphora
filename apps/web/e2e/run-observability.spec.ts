import { test, expect } from "@playwright/test";

const runId = process.env.MACRO_RUN_ID;

test.describe("run observability section", () => {
  test.skip(
    runId === undefined,
    "MACRO_RUN_ID env var required for this smoke",
  );

  test("renders inline observability tabs without console errors", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") {
        consoleErrors.push(message.text());
      }
    });
    await page.goto(`/research/runs/${runId}`);
    const section = page.getByTestId("observability-section");
    await expect(section).toBeVisible();
    await expect(section.getByText("LLM CALLS")).toBeVisible();
    await expect(section.getByText("COST LEDGER")).toBeVisible();
    await expect(section.getByText("EVIDENCE FLOW")).toBeVisible();
    await expect(section.getByText("KNOWLEDGE GRAPH")).toBeVisible();
    await expect(section.getByText("COUNTERFACTUALS")).toBeVisible();
    await expect(section.getByText("LEAKAGE")).toBeVisible();
    await expect(section.getByText("CLAIM REVIEW")).toBeVisible();
    expect(consoleErrors).toHaveLength(0);
  });
});
