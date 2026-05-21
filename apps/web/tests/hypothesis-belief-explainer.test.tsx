import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  HypothesisBeliefExplainer,
  type HypothesisBeliefBundle,
} from "@/components/research/hypothesis-belief-explainer";
import type { components } from "@/lib/api";

type HypothesisPublic = components["schemas"]["HypothesisPublic"];
type BeliefRecomputationPublic =
  components["schemas"]["BeliefRecomputationPublic"];
type BeliefInputBreakdown = components["schemas"]["BeliefInputBreakdown"];

function makeHypothesis(
  overrides: Partial<HypothesisPublic> = {},
): HypothesisPublic {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    claim_text: "Energy outperforms over next 12 weeks",
    state: "proposed",
    scope_entity_ids: [],
    scope_theme_ids: [],
    source_run_id: "00000000-0000-4000-8000-000000000002",
    entity_id: "00000000-0000-4000-8000-00000000000a",
    belief: null,
    belief_history: [],
    parent_hypothesis_id: null,
    superseded_by_id: null,
    last_activity_at: null,
    stagnation_flagged_at: null,
    archived_at: null,
    archived_reason: null,
    valid_until: null,
    created_at: "2026-05-19T12:00:00Z",
    updated_at: "2026-05-19T12:00:00Z",
    ...overrides,
  };
}

function makeInput(
  overrides: Partial<BeliefInputBreakdown> = {},
): BeliefInputBreakdown {
  return {
    relation_id: "00000000-0000-4000-8000-000000000010",
    relation_type: "supports_hypothesis",
    from_id: "00000000-0000-4000-8000-000000000011",
    to_id: "00000000-0000-4000-8000-00000000000a",
    source_id: "00000000-0000-4000-8000-000000000012",
    chunk_id: "00000000-0000-4000-8000-000000000013",
    quote: "supporting quote",
    is_explicit: true,
    sign: 1.0,
    reliability: 0.9,
    confidence: 0.8,
    relevance: 1.0,
    age_days: 10.0,
    decay: 0.93,
    weight: 0.67,
    signed_contribution: 0.67,
    ...overrides,
  };
}

function makeRecomputation(
  overrides: Partial<BeliefRecomputationPublic> = {},
): BeliefRecomputationPublic {
  return {
    id: "00000000-0000-4000-8000-000000000020",
    hypothesis_id: "00000000-0000-4000-8000-000000000001",
    computed_at: "2026-05-19T12:00:00Z",
    belief: 0.75,
    contributing_evidence_ids: [],
    computation_method: "weighted_avg_decay_v1",
    inputs: [makeInput()],
    ...overrides,
  };
}

describe("HypothesisBeliefExplainer", () => {
  it("renders an empty placeholder when no bundles are present", () => {
    render(<HypothesisBeliefExplainer bundles={[]} />);
    expect(
      screen.getByText(/no hypotheses proposed by this run/i),
    ).toBeInTheDocument();
  });

  it("renders the belief value and claim text per bundle", () => {
    const bundles: HypothesisBeliefBundle[] = [
      {
        hypothesis: makeHypothesis({ belief: 0.812 }),
        latest: makeRecomputation({ belief: 0.812 }),
      },
    ];
    render(<HypothesisBeliefExplainer bundles={bundles} />);
    expect(
      screen.getByText(/energy outperforms over next 12 weeks/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/belief 0\.812/)).toBeInTheDocument();
  });

  it("renders each input row with sign, reliability, confidence and weight", () => {
    const bundles: HypothesisBeliefBundle[] = [
      {
        hypothesis: makeHypothesis({ belief: 0.6 }),
        latest: makeRecomputation({
          inputs: [
            makeInput({
              sign: 1.0,
              reliability: 0.75,
              confidence: 0.5,
              weight: 0.375,
              signed_contribution: 0.375,
            }),
            makeInput({
              relation_id: "00000000-0000-4000-8000-000000000099",
              relation_type: "contradicts_hypothesis",
              sign: -1.0,
              weight: 0.2,
              signed_contribution: -0.2,
            }),
          ],
        }),
      },
    ];
    render(<HypothesisBeliefExplainer bundles={bundles} />);
    expect(screen.getByText("supports_hypothesis")).toBeInTheDocument();
    expect(screen.getByText("contradicts_hypothesis")).toBeInTheDocument();
    expect(screen.getByText("+1.00")).toBeInTheDocument();
    expect(screen.getByText("-1.00")).toBeInTheDocument();
    expect(screen.getByText(/over 2 relations/i)).toBeInTheDocument();
  });

  it("falls back to a neutral-prior message when latest has no inputs", () => {
    const bundles: HypothesisBeliefBundle[] = [
      {
        hypothesis: makeHypothesis({ belief: 0.5 }),
        latest: makeRecomputation({ belief: 0.5, inputs: [] }),
      },
    ];
    render(<HypothesisBeliefExplainer bundles={bundles} />);
    expect(
      screen.getByText(/returned the neutral prior \(0\.5\)/i),
    ).toBeInTheDocument();
  });

  it("falls back to the never-computed message when there is no latest row", () => {
    const bundles: HypothesisBeliefBundle[] = [
      { hypothesis: makeHypothesis({ belief: null }), latest: null },
    ];
    render(<HypothesisBeliefExplainer bundles={bundles} />);
    expect(
      screen.getByText(/no belief has been computed yet/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/belief —/)).toBeInTheDocument();
  });
});
