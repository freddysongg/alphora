import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { CostLedger } from "@/components/research/cost-ledger";
import type { components } from "@/lib/api";

type RunCostLedger = components["schemas"]["RunCostLedger"];

const RUN_ID = "11111111-1111-4111-8111-111111111111";

function makeLedger(overrides: Partial<RunCostLedger> = {}): RunCostLedger {
  return {
    run_id: RUN_ID,
    total_cost_usd: "0.450000",
    total_calls: 3,
    total_input_tokens: 1200,
    total_output_tokens: 600,
    total_cached_input_tokens: 400,
    cache_hit_rate: 1 / 3,
    stages: [
      {
        stage: "extraction",
        call_count: 1,
        total_cost_usd: "0.050000",
        total_input_tokens: 200,
        total_output_tokens: 100,
        total_cached_input_tokens: 0,
        cache_hit_rate: 0,
        models: ["gpt-5-mini"],
      },
      {
        stage: "macro_synthesis",
        call_count: 2,
        total_cost_usd: "0.400000",
        total_input_tokens: 1000,
        total_output_tokens: 500,
        total_cached_input_tokens: 400,
        cache_hit_rate: 0.4,
        models: ["gpt-5", "gpt-5-mini"],
      },
    ],
    ...overrides,
  };
}

describe("CostLedger", () => {
  it("renders an empty placeholder when no stages have data", () => {
    render(<CostLedger ledger={null} />);
    expect(
      screen.getByText("No LLM cost recorded for this run yet."),
    ).toBeInTheDocument();
  });

  it("renders the summary totals and per-stage rows", () => {
    render(<CostLedger ledger={makeLedger()} />);
    const totals = screen.getByTestId("cost-ledger-totals");
    expect(totals.textContent).toContain("$0.4500");
    expect(totals.textContent).toContain("3");
    expect(totals.textContent).toContain("33.3%");
    const table = screen.getByTestId("cost-ledger-table");
    expect(table.textContent).toContain("extraction");
    expect(table.textContent).toContain("macro_synthesis");
    expect(table.textContent).toContain("$0.4000");
    expect(table.textContent).toContain("$0.0500");
  });

  it("renders the chart container when stages exist", () => {
    render(<CostLedger ledger={makeLedger()} />);
    expect(screen.getByTestId("cost-ledger-chart")).toBeInTheDocument();
  });

  it("lists multiple models per stage joined with comma", () => {
    render(<CostLedger ledger={makeLedger()} />);
    expect(screen.getByText("gpt-5, gpt-5-mini")).toBeInTheDocument();
  });
});
