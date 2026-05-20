import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { CounterfactualMatrix } from "@/components/research/counterfactual-matrix";
import type { components } from "@/lib/api";

type Perturbation = components["schemas"]["CounterfactualPerturbationPublic"];

const RUN_ID = "11111111-1111-4111-8111-111111111111";

function makePerturbation(
  overrides: Partial<Perturbation> & {
    id?: string;
    brief_kind?: Perturbation["brief_kind"];
    perturbation_kind?: Perturbation["perturbation_kind"];
  } = {},
): Perturbation {
  return {
    id: overrides.id ?? crypto.randomUUID(),
    run_id: RUN_ID,
    brief_kind: overrides.brief_kind ?? "macro",
    brief_id: "22222222-2222-4222-8222-222222222222",
    perturbation_kind: overrides.perturbation_kind ?? "drop_top_evidence",
    perturbation_input: { kind: "drop", target: "ev-1" },
    baseline_output: { calls: [] },
    perturbed_output: { calls: [] },
    decision_delta: { changed: false },
    is_meaningful: true,
    decision_changed: false,
    created_at: "2026-05-20T10:00:00.000Z",
    ...overrides,
  };
}

describe("CounterfactualMatrix", () => {
  it("renders an empty placeholder when there are no perturbations", () => {
    render(<CounterfactualMatrix perturbations={[]} />);
    expect(
      screen.getByText("No counterfactual perturbations recorded for this run yet."),
    ).toBeInTheDocument();
  });

  it("renders a row per brief with cells per perturbation_kind", () => {
    render(
      <CounterfactualMatrix
        perturbations={[
          makePerturbation({
            id: "a",
            brief_kind: "macro",
            perturbation_kind: "drop_top_evidence",
            decision_changed: true,
          }),
          makePerturbation({
            id: "b",
            brief_kind: "macro",
            perturbation_kind: "flip_top_call_direction",
            decision_changed: false,
          }),
        ]}
      />,
    );
    const rows = screen.getAllByTestId("counterfactual-matrix-row");
    expect(rows).toHaveLength(1);
    const cells = screen.getAllByTestId("counterfactual-matrix-cell");
    expect(cells.length).toBe(5);
    const changed = cells.find((cell) => cell.getAttribute("data-cell-state") === "changed");
    expect(changed?.textContent).toBe("changed");
    const stable = cells.find((cell) => cell.getAttribute("data-cell-state") === "stable");
    expect(stable?.textContent).toBe("stable");
  });

  it("marks non-meaningful perturbations as no-op without danger styling", () => {
    render(
      <CounterfactualMatrix
        perturbations={[
          makePerturbation({
            perturbation_kind: "swap_call_ordering",
            is_meaningful: false,
            decision_changed: false,
          }),
        ]}
      />,
    );
    const cells = screen.getAllByTestId("counterfactual-matrix-cell");
    const noop = cells.find((cell) => cell.getAttribute("data-cell-state") === "no-op");
    expect(noop?.textContent).toBe("no-op");
    expect(noop?.className).not.toContain("text-danger");
  });

  it("groups multiple briefs into separate rows", () => {
    render(
      <CounterfactualMatrix
        perturbations={[
          makePerturbation({
            id: "a",
            brief_kind: "macro",
            perturbation_kind: "drop_top_evidence",
          }),
          makePerturbation({
            id: "b",
            brief_kind: "company",
            brief_id: "33333333-3333-4333-8333-333333333333",
            perturbation_kind: "drop_top_evidence",
          }),
        ]}
      />,
    );
    const rows = screen.getAllByTestId("counterfactual-matrix-row");
    expect(rows).toHaveLength(2);
  });
});
