import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { CounterfactualGateSummary } from "@/components/research/counterfactual-gate-summary";
import type { components } from "@/lib/api";

type GateRow = components["schemas"]["CounterfactualGateRunPublic"];

function makeGate(overrides: Partial<GateRow> = {}): GateRow {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    run_id: "00000000-0000-4000-8000-000000000002",
    brief_kind: "macro",
    brief_id: "00000000-0000-4000-8000-000000000003",
    perturbation_count: 5,
    meaningful_count: 4,
    meaningful_changed_count: 3,
    change_rate: 0.75,
    threshold: 0.5,
    passed: true,
    created_at: "2026-05-19T12:00:00Z",
    ...overrides,
  };
}

describe("CounterfactualGateSummary", () => {
  it("renders an empty placeholder when no gates are present", () => {
    render(<CounterfactualGateSummary gates={[]} />);
    expect(
      screen.getByText(/no counterfactual perturbations recorded/i),
    ).toBeInTheDocument();
  });

  it("renders meaningful counts and change-rate percent for each gate", () => {
    render(
      <CounterfactualGateSummary
        gates={[
          makeGate({
            brief_kind: "macro",
            meaningful_count: 4,
            meaningful_changed_count: 3,
            change_rate: 0.75,
            passed: true,
          }),
          makeGate({
            id: "00000000-0000-4000-8000-000000000099",
            brief_kind: "sector",
            meaningful_count: 4,
            meaningful_changed_count: 1,
            change_rate: 0.25,
            passed: false,
          }),
        ]}
      />,
    );
    expect(screen.getByText("MACRO")).toBeInTheDocument();
    expect(screen.getByText("SECTOR")).toBeInTheDocument();
    expect(screen.getByText("3/4 meaningful changed")).toBeInTheDocument();
    expect(screen.getByText("1/4 meaningful changed")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
  });

  it("renders failed change-rate with the danger tone class", () => {
    render(
      <CounterfactualGateSummary
        gates={[
          makeGate({
            change_rate: 0.25,
            passed: false,
          }),
        ]}
      />,
    );
    const failingRate = screen.getByText("25%");
    expect(failingRate.className).toContain("text-danger");
  });
});
