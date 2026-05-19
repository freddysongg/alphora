import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { SectorBriefCard } from "@/components/research/sector-brief-card";
import type { components } from "@/lib/api";

type SectorBriefPublic = components["schemas"]["SectorBriefPublic"];

function makeSectorBrief(
  overrides: Partial<SectorBriefPublic["brief"]> = {},
  judgeOverrides: Partial<SectorBriefPublic["judge"]> = {},
): SectorBriefPublic {
  return {
    brief: {
      sector_entity_id: "00000000-0000-4000-8000-000000000001",
      sector_name: "Information Technology",
      direction: "overweight",
      themes: [],
      companies: [
        {
          name: "Apple",
          ticker: "AAPL",
          direction: "overweight",
          conviction: 0.8,
          evidence_ids: [],
        },
      ],
      watch_items: [],
      cited_claims: [],
      confidence: 0.75,
      verifier_status: "verified",
      regeneration_count: 0,
      ...overrides,
    },
    judge: {
      status: "passed",
      reasons: [],
      call_id: null,
      ...judgeOverrides,
    },
  };
}

describe("SectorBriefCard", () => {
  it("renders sector name, direction badge, and conviction percentage", () => {
    render(<SectorBriefCard sectorBrief={makeSectorBrief()} />);
    expect(screen.getByText("Information Technology")).toBeInTheDocument();
    expect(screen.getByText("overweight")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
    const bar = screen.getByRole("progressbar", { name: "conviction" });
    expect(bar).toHaveAttribute("aria-valuenow", "75");
  });

  it("surfaces the judge status badge", () => {
    render(
      <SectorBriefCard
        sectorBrief={makeSectorBrief({}, { status: "flagged" })}
      />,
    );
    expect(screen.getByText("flagged")).toBeInTheDocument();
  });

  it("lists company ideas with ticker", () => {
    render(<SectorBriefCard sectorBrief={makeSectorBrief()} />);
    expect(screen.getByText("Apple")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });

  it("clamps conviction outside [0,1] to 0..100", () => {
    render(
      <SectorBriefCard
        sectorBrief={makeSectorBrief({ confidence: 1.5 })}
      />,
    );
    const bar = screen.getByRole("progressbar", { name: "conviction" });
    expect(bar).toHaveAttribute("aria-valuenow", "100");
  });
});
