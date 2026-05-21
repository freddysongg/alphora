import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { LeakageChart } from "@/components/research/leakage-chart";
import type { components } from "@/lib/api";

type LeakageRun = components["schemas"]["LeakageRunPublic"];

function makeRun(overrides: Partial<LeakageRun> = {}): LeakageRun {
  return {
    id: overrides.id ?? crypto.randomUUID(),
    run_id: null,
    case_count: 5,
    mean_decay: 0.18,
    max_decay: 0.34,
    threshold: 0.3,
    flagged: false,
    case_ids: [],
    created_at: "2026-05-15T10:00:00.000Z",
    ...overrides,
  };
}

describe("LeakageChart", () => {
  it("renders an empty placeholder when there are no leakage runs", () => {
    render(<LeakageChart runs={[]} />);
    expect(
      screen.getByText("No leakage holdout runs recorded yet."),
    ).toBeInTheDocument();
  });

  it("renders the summary line with run count and flagged count", () => {
    render(
      <LeakageChart
        runs={[
          makeRun({ id: "a", flagged: false }),
          makeRun({ id: "b", flagged: true, created_at: "2026-05-16T10:00:00.000Z" }),
        ]}
      />,
    );
    const summary = screen.getByTestId("leakage-chart-summary");
    expect(summary.textContent).toContain("2 RUNS");
    expect(summary.textContent).toContain("1 FLAGGED");
    expect(summary.textContent).toContain("30.0%");
  });

  it("renders a row per leakage run with formatted percentages", () => {
    render(
      <LeakageChart
        runs={[
          makeRun({ id: "a", mean_decay: 0.1, max_decay: 0.4 }),
        ]}
      />,
    );
    const rows = screen.getAllByTestId("leakage-chart-row");
    expect(rows).toHaveLength(1);
    expect(rows[0]?.textContent).toContain("10.0%");
    expect(rows[0]?.textContent).toContain("40.0%");
  });

  it("marks flagged runs in danger tone", () => {
    render(
      <LeakageChart
        runs={[makeRun({ id: "a", flagged: true })]}
      />,
    );
    const flagged = screen.getByText("flagged");
    expect(flagged.className).toContain("text-danger");
  });
});
