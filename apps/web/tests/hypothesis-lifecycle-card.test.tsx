import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  HypothesisLifecycleCard,
  type HypothesisLifecycleBundle,
} from "@/components/research/hypothesis-lifecycle-card";
import type { components } from "@/lib/api";

type HypothesisPublic = components["schemas"]["HypothesisPublic"];
type HypothesisLifecycleResponse =
  components["schemas"]["HypothesisLifecycleResponse"];
type ConditionalEdgePublic =
  components["schemas"]["ConditionalEdgePublic"];
type EventResolutionPublic =
  components["schemas"]["EventResolutionPublic"];

function makeHypothesis(
  overrides: Partial<HypothesisPublic> = {},
): HypothesisPublic {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    claim_text: "Energy outperforms over next 12 weeks",
    state: "active",
    scope_entity_ids: [],
    scope_theme_ids: [],
    source_run_id: "00000000-0000-4000-8000-000000000002",
    entity_id: "00000000-0000-4000-8000-00000000000a",
    belief: 0.6,
    belief_history: [],
    parent_hypothesis_id: null,
    superseded_by_id: null,
    last_activity_at: "2026-05-20T10:00:00Z",
    stagnation_flagged_at: null,
    archived_at: null,
    archived_reason: null,
    valid_until: null,
    created_at: "2026-05-19T12:00:00Z",
    updated_at: "2026-05-19T12:00:00Z",
    ...overrides,
  };
}

function makeLifecycle(
  hypothesis: HypothesisPublic,
  overrides: Partial<HypothesisLifecycleResponse> = {},
): HypothesisLifecycleResponse {
  return {
    hypothesis,
    parent: null,
    children: [],
    supersedes: null,
    superseded_by: null,
    conditional_edges: [],
    recent_event_resolutions: [],
    ...overrides,
  };
}

describe("HypothesisLifecycleCard", () => {
  it("renders an empty placeholder when no bundles are provided", () => {
    render(<HypothesisLifecycleCard bundles={[]} />);
    expect(
      screen.getByText(/no hypotheses with lifecycle state/i),
    ).toBeInTheDocument();
  });

  it("renders the hypothesis state, last activity and archived placeholder", () => {
    const hypothesis = makeHypothesis();
    const bundles: HypothesisLifecycleBundle[] = [
      { hypothesis, lifecycle: makeLifecycle(hypothesis) },
    ];
    render(<HypothesisLifecycleCard bundles={bundles} />);
    expect(screen.getByText(/active/i)).toBeInTheDocument();
    expect(
      screen.getByText(/energy outperforms over next 12 weeks/i),
    ).toBeInTheDocument();
    expect(screen.getByText("2026-05-20T10:00:00.000Z")).toBeInTheDocument();
  });

  it("renders the stagnation timestamp when flagged", () => {
    const hypothesis = makeHypothesis({
      stagnation_flagged_at: "2026-05-25T03:00:00Z",
    });
    const bundles: HypothesisLifecycleBundle[] = [
      { hypothesis, lifecycle: makeLifecycle(hypothesis) },
    ];
    render(<HypothesisLifecycleCard bundles={bundles} />);
    expect(screen.getByText("2026-05-25T03:00:00.000Z")).toBeInTheDocument();
  });

  it("renders the archived reason for terminal hypotheses", () => {
    const hypothesis = makeHypothesis({
      state: "expired",
      archived_at: "2026-05-30T00:00:00Z",
      archived_reason: "belief_floor",
    });
    const bundles: HypothesisLifecycleBundle[] = [
      { hypothesis, lifecycle: makeLifecycle(hypothesis) },
    ];
    render(<HypothesisLifecycleCard bundles={bundles} />);
    expect(
      screen.getByText(/2026-05-30T00:00:00.000Z \(belief_floor\)/),
    ).toBeInTheDocument();
  });

  it("renders parent, supersedes and superseded by relations when present", () => {
    const hypothesis = makeHypothesis({ id: "00000000-0000-4000-8000-000000000050" });
    const parent = makeHypothesis({
      id: "00000000-0000-4000-8000-000000000051",
      claim_text: "parent claim",
    });
    const supersedes = makeHypothesis({
      id: "00000000-0000-4000-8000-000000000052",
      claim_text: "previous framing",
    });
    const supersededBy = makeHypothesis({
      id: "00000000-0000-4000-8000-000000000053",
      claim_text: "new framing",
    });
    const bundles: HypothesisLifecycleBundle[] = [
      {
        hypothesis,
        lifecycle: makeLifecycle(hypothesis, {
          parent,
          supersedes,
          superseded_by: supersededBy,
        }),
      },
    ];
    render(<HypothesisLifecycleCard bundles={bundles} />);
    expect(screen.getByText("parent claim")).toBeInTheDocument();
    expect(screen.getByText("previous framing")).toBeInTheDocument();
    expect(screen.getByText("new framing")).toBeInTheDocument();
  });

  it("lists children when the hypothesis has descendants", () => {
    const hypothesis = makeHypothesis();
    const childA = makeHypothesis({
      id: "00000000-0000-4000-8000-000000000060",
      claim_text: "child a",
    });
    const childB = makeHypothesis({
      id: "00000000-0000-4000-8000-000000000061",
      claim_text: "child b",
    });
    const bundles: HypothesisLifecycleBundle[] = [
      {
        hypothesis,
        lifecycle: makeLifecycle(hypothesis, { children: [childA, childB] }),
      },
    ];
    render(<HypothesisLifecycleCard bundles={bundles} />);
    expect(screen.getByText("child a")).toBeInTheDocument();
    expect(screen.getByText("child b")).toBeInTheDocument();
  });

  it("renders conditional edges and recent event resolutions", () => {
    const hypothesis = makeHypothesis();
    const conditionalEdges: ConditionalEdgePublic[] = [
      {
        relation_id: "00000000-0000-4000-8000-000000000071",
        relation_type: "validates_if_beat",
        event_entity_id: "00000000-0000-4000-8000-000000000072",
        event_entity_name: "NVDA Q3 earnings",
      },
    ];
    const recentResolutions: EventResolutionPublic[] = [
      {
        id: "00000000-0000-4000-8000-000000000080",
        event_entity_id: "00000000-0000-4000-8000-000000000072",
        kind: "beat",
        resolved_at: "2026-05-22T15:00:00Z",
        source_id: null,
        notes: "EPS exceeded",
        payload: null,
        created_at: "2026-05-22T15:00:00Z",
      },
    ];
    const bundles: HypothesisLifecycleBundle[] = [
      {
        hypothesis,
        lifecycle: makeLifecycle(hypothesis, {
          conditional_edges: conditionalEdges,
          recent_event_resolutions: recentResolutions,
        }),
      },
    ];
    render(<HypothesisLifecycleCard bundles={bundles} />);
    expect(screen.getByText("validates_if_beat")).toBeInTheDocument();
    expect(screen.getByText("NVDA Q3 earnings")).toBeInTheDocument();
    expect(screen.getByText("beat")).toBeInTheDocument();
    expect(screen.getByText("EPS exceeded")).toBeInTheDocument();
  });

  it("renders gracefully when lifecycle is null", () => {
    const hypothesis = makeHypothesis();
    const bundles: HypothesisLifecycleBundle[] = [
      { hypothesis, lifecycle: null },
    ];
    render(<HypothesisLifecycleCard bundles={bundles} />);
    expect(
      screen.getByText(/energy outperforms over next 12 weeks/i),
    ).toBeInTheDocument();
  });
});
