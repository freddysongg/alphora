import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { MacroBriefDetail } from "@/app/(app)/research/runs/[id]/macro-brief-detail";
import type { components } from "@/lib/api";

type MacroBriefPublic = components["schemas"]["MacroBriefPublic"];

function makeData(
  overrides: Partial<MacroBriefPublic> = {},
): MacroBriefPublic {
  return {
    brief: {
      themes: [
        { name: "AI Capex", evidence_ids: [], confidence: 0.8 },
      ],
      sector_calls: [
        {
          sector_entity_id: "00000000-0000-4000-8000-000000000001",
          sector_name: "Information Technology",
          direction: "overweight",
          conviction: 0.85,
          evidence_ids: [],
        },
      ],
      watch_items: [],
      cited_claims: [],
      proposed_hypotheses: [],
      confidence: 0.7,
      evidence_ids: [],
      verifier_status: "verified",
      regeneration_count: 0,
    },
    judge: {
      status: "passed",
      reasons: [],
      call_id: null,
    },
    chunks: [],
    sector_briefs: [
      {
        brief: {
          sector_entity_id: "00000000-0000-4000-8000-000000000001",
          sector_name: "Information Technology",
          direction: "overweight",
          themes: [],
          companies: [],
          watch_items: [],
          cited_claims: [],
          confidence: 0.8,
          verifier_status: "verified",
          regeneration_count: 0,
        },
        judge: { status: "passed", reasons: [], call_id: null },
      },
    ],
    ...overrides,
  };
}

describe("MacroBriefDetail", () => {
  it("renders themes, sector calls, judge badge, and sector brief cards", () => {
    render(<MacroBriefDetail data={makeData()} />);
    expect(screen.getByText("AI Capex")).toBeInTheDocument();
    expect(
      screen.getAllByText("Information Technology").length,
    ).toBeGreaterThan(0);
    expect(screen.getByTestId("judge-badge")).toHaveTextContent(/passed/i);
    expect(screen.getAllByTestId("sector-brief-card")).toHaveLength(1);
  });

  it("shows the JUDGE NOT RUN badge when judge.status is not_run", () => {
    render(
      <MacroBriefDetail
        data={makeData({
          judge: { status: "not_run", reasons: [], call_id: null },
        })}
      />,
    );
    expect(screen.getByTestId("judge-badge")).toHaveTextContent(/not run/i);
  });

  it("shows the empty state when there are no sector briefs", () => {
    render(
      <MacroBriefDetail
        data={makeData({ sector_briefs: [] })}
      />,
    );
    expect(screen.queryByTestId("sector-brief-card")).not.toBeInTheDocument();
  });
});
