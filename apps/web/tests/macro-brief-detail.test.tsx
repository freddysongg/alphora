import { describe, it, expect } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { MacroBriefDetail } from "@/app/(app)/research/runs/[id]/macro-brief-detail";
import type { components } from "@/lib/api";

type MacroBriefPublic = components["schemas"]["MacroBriefPublic"];

const MACRO_CHUNK_ID = "00000000-0000-4000-8000-0000000000aa";
const SECTOR_CALL_EVIDENCE_ID_1 = "00000000-0000-4000-8000-0000000000c1";
const SECTOR_CALL_EVIDENCE_ID_2 = "00000000-0000-4000-8000-0000000000c2";
const MACRO_THEME_EVIDENCE_ID_1 = "00000000-0000-4000-8000-0000000000d1";
const MACRO_THEME_EVIDENCE_ID_2 = "00000000-0000-4000-8000-0000000000d2";
const MACRO_WATCH_EVIDENCE_ID_1 = "00000000-0000-4000-8000-0000000000e1";
const MACRO_WATCH_EVIDENCE_ID_2 = "00000000-0000-4000-8000-0000000000e2";
const MACRO_HYPOTHESIS_EVIDENCE_ID_1 = "00000000-0000-4000-8000-0000000000f1";
const MACRO_HYPOTHESIS_EVIDENCE_ID_2 = "00000000-0000-4000-8000-0000000000f2";

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

  it("links the expanded cited claim chunk_id to the evidence trace page and preserves the chunk preview", () => {
    const data = makeData({
      brief: {
        themes: [],
        sector_calls: [],
        watch_items: [],
        cited_claims: [
          {
            claim_text: "AI capex remains a multi-year tailwind.",
            exact_quote: "AI capex is forecast to grow 30% in 2026.",
            chunk_id: MACRO_CHUNK_ID,
            source: "10-Q",
          },
        ],
        proposed_hypotheses: [],
        confidence: 0.7,
        evidence_ids: [],
        verifier_status: "verified",
        regeneration_count: 0,
      },
      chunks: [
        {
          chunk_id: MACRO_CHUNK_ID,
          evidence_id: "00000000-0000-4000-8000-0000000000bb",
          source: "10-Q",
          text: "AI capex is forecast to grow 30% in 2026 as hyperscalers ramp.",
          attributes: {},
        },
      ],
    });
    render(<MacroBriefDetail data={data} />);
    const row = screen.getByTestId("macro-cited-claim-row");
    const trigger = within(row).getByRole("button");
    fireEvent.click(trigger);
    const link = within(row).getByTestId("macro-cited-claim-chunk-link");
    expect(link).toHaveAttribute("href", `/research/evidence/${MACRO_CHUNK_ID}`);
    expect(link).toHaveTextContent(MACRO_CHUNK_ID);
    expect(
      within(row).getByText(/AI capex is forecast to grow 30% in 2026\./),
    ).toBeInTheDocument();
    expect(
      within(row).getByText(/hyperscalers ramp/),
    ).toBeInTheDocument();
  });

  it("expands the sector call evidence cell into one trace link per evidence_id", () => {
    const data = makeData({
      brief: {
        themes: [],
        sector_calls: [
          {
            sector_entity_id: "00000000-0000-4000-8000-000000000001",
            sector_name: "Information Technology",
            direction: "overweight",
            conviction: 0.85,
            evidence_ids: [
              SECTOR_CALL_EVIDENCE_ID_1,
              SECTOR_CALL_EVIDENCE_ID_2,
            ],
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
    });
    render(<MacroBriefDetail data={data} />);
    const row = screen.getByTestId("macro-sector-call-row");
    const trigger = within(row).getByRole("button");
    fireEvent.click(trigger);
    const links = within(row).getAllByTestId("macro-sector-call-evidence-link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${SECTOR_CALL_EVIDENCE_ID_1}`,
    );
    expect(links[0]).toHaveTextContent(SECTOR_CALL_EVIDENCE_ID_1);
    expect(links[1]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${SECTOR_CALL_EVIDENCE_ID_2}`,
    );
    expect(links[1]).toHaveTextContent(SECTOR_CALL_EVIDENCE_ID_2);
  });

  it("expands the theme evidence list into one trace link per evidence_id", () => {
    const data = makeData({
      brief: {
        themes: [
          {
            name: "AI Capex",
            evidence_ids: [
              MACRO_THEME_EVIDENCE_ID_1,
              MACRO_THEME_EVIDENCE_ID_2,
            ],
            confidence: 0.8,
          },
        ],
        sector_calls: [],
        watch_items: [],
        cited_claims: [],
        proposed_hypotheses: [],
        confidence: 0.7,
        evidence_ids: [],
        verifier_status: "verified",
        regeneration_count: 0,
      },
    });
    render(<MacroBriefDetail data={data} />);
    const row = screen.getByTestId("macro-theme-row");
    const trigger = within(row).getByRole("button");
    fireEvent.click(trigger);
    const links = within(row).getAllByTestId("macro-theme-evidence-link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${MACRO_THEME_EVIDENCE_ID_1}`,
    );
    expect(links[0]).toHaveTextContent(MACRO_THEME_EVIDENCE_ID_1);
    expect(links[1]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${MACRO_THEME_EVIDENCE_ID_2}`,
    );
    expect(links[1]).toHaveTextContent(MACRO_THEME_EVIDENCE_ID_2);
  });

  it("expands the watch item evidence list into one trace link per evidence_id", () => {
    const data = makeData({
      brief: {
        themes: [],
        sector_calls: [],
        watch_items: [
          {
            name: "10y yields",
            reason: "Approaching the 5% threshold.",
            evidence_ids: [
              MACRO_WATCH_EVIDENCE_ID_1,
              MACRO_WATCH_EVIDENCE_ID_2,
            ],
          },
        ],
        cited_claims: [],
        proposed_hypotheses: [],
        confidence: 0.6,
        evidence_ids: [],
        verifier_status: "verified",
        regeneration_count: 0,
      },
    });
    render(<MacroBriefDetail data={data} />);
    const row = screen.getByTestId("macro-watch-item-row");
    const trigger = within(row).getByRole("button");
    fireEvent.click(trigger);
    const links = within(row).getAllByTestId("macro-watch-item-evidence-link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${MACRO_WATCH_EVIDENCE_ID_1}`,
    );
    expect(links[0]).toHaveTextContent(MACRO_WATCH_EVIDENCE_ID_1);
    expect(links[1]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${MACRO_WATCH_EVIDENCE_ID_2}`,
    );
    expect(links[1]).toHaveTextContent(MACRO_WATCH_EVIDENCE_ID_2);
  });

  it("expands the proposed hypothesis evidence list into one trace link per evidence_id", () => {
    const data = makeData({
      brief: {
        themes: [],
        sector_calls: [],
        watch_items: [],
        cited_claims: [],
        proposed_hypotheses: [
          {
            claim_text: "Rate cuts repriced into 2026.",
            scope_entity_ids: [],
            evidence_ids: [
              MACRO_HYPOTHESIS_EVIDENCE_ID_1,
              MACRO_HYPOTHESIS_EVIDENCE_ID_2,
            ],
          },
        ],
        confidence: 0.55,
        evidence_ids: [],
        verifier_status: "verified",
        regeneration_count: 0,
      },
    });
    render(<MacroBriefDetail data={data} />);
    const row = screen.getByTestId("macro-hypothesis-row");
    const trigger = within(row).getByRole("button");
    fireEvent.click(trigger);
    const links = within(row).getAllByTestId("macro-hypothesis-evidence-link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${MACRO_HYPOTHESIS_EVIDENCE_ID_1}`,
    );
    expect(links[0]).toHaveTextContent(MACRO_HYPOTHESIS_EVIDENCE_ID_1);
    expect(links[1]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${MACRO_HYPOTHESIS_EVIDENCE_ID_2}`,
    );
    expect(links[1]).toHaveTextContent(MACRO_HYPOTHESIS_EVIDENCE_ID_2);
  });

  it("renders the evidence link even when the chunk lookup is missing", () => {
    const data = makeData({
      brief: {
        themes: [],
        sector_calls: [],
        watch_items: [],
        cited_claims: [
          {
            claim_text: "Inflation surprises are skewed hotter.",
            exact_quote: "CPI prints have run hotter than consensus.",
            chunk_id: MACRO_CHUNK_ID,
            source: "BLS",
          },
        ],
        proposed_hypotheses: [],
        confidence: 0.6,
        evidence_ids: [],
        verifier_status: "verified",
        regeneration_count: 0,
      },
      chunks: [],
    });
    render(<MacroBriefDetail data={data} />);
    const row = screen.getByTestId("macro-cited-claim-row");
    const trigger = within(row).getByRole("button");
    fireEvent.click(trigger);
    const link = within(row).getByTestId("macro-cited-claim-chunk-link");
    expect(link).toHaveAttribute("href", `/research/evidence/${MACRO_CHUNK_ID}`);
  });
});
