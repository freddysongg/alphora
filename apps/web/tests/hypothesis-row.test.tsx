import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

import { HypothesisRow } from "@/components/research/hypothesis-row";
import type { components } from "@/lib/api";

vi.mock("@/app/(app)/research/hypotheses/actions", () => ({
  activateHypothesis: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

type HypothesisPublic = components["schemas"]["HypothesisPublic"];

function makeHypothesis(
  overrides: Partial<HypothesisPublic> = {},
): HypothesisPublic {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    claim_text: "Capex on AI compute outpaces consensus",
    state: "proposed",
    scope_entity_ids: [],
    scope_theme_ids: [],
    source_run_id: "00000000-0000-4000-8000-000000000002",
    created_at: "2026-05-19T12:00:00Z",
    updated_at: "2026-05-19T12:00:00Z",
    ...overrides,
  };
}

describe("HypothesisRow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows activate button when state is proposed", () => {
    render(<HypothesisRow hypothesis={makeHypothesis()} />);
    expect(
      screen.getByRole("button", { name: /activate hypothesis/i }),
    ).toBeInTheDocument();
  });

  it("hides activate button when state is active", () => {
    render(
      <HypothesisRow hypothesis={makeHypothesis({ state: "active" })} />,
    );
    expect(
      screen.queryByRole("button", { name: /activate hypothesis/i }),
    ).not.toBeInTheDocument();
  });

  it("renders the claim text", () => {
    render(<HypothesisRow hypothesis={makeHypothesis()} />);
    expect(
      screen.getByText(/capex on ai compute outpaces consensus/i),
    ).toBeInTheDocument();
  });

  it("renders the state caps label", () => {
    render(<HypothesisRow hypothesis={makeHypothesis()} />);
    expect(screen.getByText(/proposed/i)).toBeInTheDocument();
  });
});
