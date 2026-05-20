import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  RunCostMeter,
  type CostMeterState,
} from "@/components/research/run-cost-meter";

const RUN_ID = "11111111-1111-4111-8111-111111111111";

function makeState(overrides: Partial<CostMeterState> = {}): CostMeterState {
  return {
    cumulativeCostUsd: 0,
    inputTokensTotal: 0,
    cachedInputTokensTotal: 0,
    lastModel: null,
    lastBudgetAction: null,
    ...overrides,
  };
}

describe("RunCostMeter", () => {
  it("renders the initial cumulative cost, cached ratio, model, and budget action when the run is terminal", () => {
    render(
      <RunCostMeter
        runId={RUN_ID}
        initialState={makeState({
          cumulativeCostUsd: 0.5432,
          inputTokensTotal: 1000,
          cachedInputTokensTotal: 250,
          lastModel: "gpt-5",
          lastBudgetAction: "allow",
        })}
        initialSeenLogIds={[]}
        isTerminal={true}
      />,
    );

    expect(screen.getByText("CUMULATIVE COST")).toBeInTheDocument();
    expect(screen.getByText("$0.5432")).toBeInTheDocument();
    expect(screen.getByText("CACHED RATIO")).toBeInTheDocument();
    expect(screen.getByText("25.0%")).toBeInTheDocument();
    expect(screen.getByText("MODEL")).toBeInTheDocument();
    expect(screen.getByText("gpt-5")).toBeInTheDocument();
    expect(screen.getByText("BUDGET ACTION")).toBeInTheDocument();
    expect(screen.getByText("ALLOW")).toBeInTheDocument();
  });

  it("renders em-dashes when there is no model, action, or input token data yet", () => {
    render(
      <RunCostMeter
        runId={RUN_ID}
        initialState={makeState()}
        initialSeenLogIds={[]}
        isTerminal={true}
      />,
    );

    expect(screen.getByText("$0.0000")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
  });

  it("formats cumulative cost to four decimal places", () => {
    render(
      <RunCostMeter
        runId={RUN_ID}
        initialState={makeState({ cumulativeCostUsd: 12.3456789 })}
        initialSeenLogIds={[]}
        isTerminal={true}
      />,
    );

    expect(screen.getByText("$12.3457")).toBeInTheDocument();
  });

  it("renders a kill budget action with the danger tone class", () => {
    render(
      <RunCostMeter
        runId={RUN_ID}
        initialState={makeState({ lastBudgetAction: "kill" })}
        initialSeenLogIds={[]}
        isTerminal={true}
      />,
    );

    const killNode = screen.getByText("KILL");
    expect(killNode.className).toContain("text-danger");
  });

  it("renders a warn budget action carried over from the initial state on a terminal run, preserving the warn signal across reload", () => {
    render(
      <RunCostMeter
        runId={RUN_ID}
        initialState={makeState({ lastBudgetAction: "warn" })}
        initialSeenLogIds={["log-1", "log-2"]}
        isTerminal={true}
      />,
    );

    expect(screen.getByText("WARN")).toBeInTheDocument();
  });
});
