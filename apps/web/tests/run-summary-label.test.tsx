import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { RunRow } from "@/app/(app)/research/runs/run-row";
import type { components } from "@/lib/api";

type ResearchRunSummary = components["schemas"]["ResearchRunSummary"];

function makeRun(overrides: Partial<ResearchRunSummary> = {}): ResearchRunSummary {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    ticker: null,
    strategy: "funnel_research",
    status: "succeeded",
    final_rating: null,
    created_at: "2026-05-19T12:00:00Z",
    scope_payload: { kind: "macro", universe: "us_equities" },
    ...overrides,
  };
}

describe("RunRow label", () => {
  it("renders MACRO · US EQUITIES for funnel_research runs", () => {
    render(
      <ul>
        <RunRow run={makeRun()} />
      </ul>,
    );
    expect(screen.getByText(/MACRO · US EQUITIES/)).toBeInTheDocument();
  });

  it("falls back to ticker for tradingagents runs", () => {
    render(
      <ul>
        <RunRow
          run={makeRun({
            strategy: "tradingagents",
            ticker: "AAPL",
            scope_payload: null,
          })}
        />
      </ul>,
    );
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.queryByText(/MACRO · US EQUITIES/)).not.toBeInTheDocument();
  });

  it("uses scope.kind + scope.universe even when ticker is also present", () => {
    render(
      <ul>
        <RunRow
          run={makeRun({
            strategy: "funnel_research",
            ticker: "AAPL",
            scope_payload: { kind: "macro", universe: "us_equities" },
          })}
        />
      </ul>,
    );
    expect(screen.getByText(/MACRO · US EQUITIES/)).toBeInTheDocument();
  });
});
