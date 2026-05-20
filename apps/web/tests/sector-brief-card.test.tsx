import { describe, it, expect } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { SectorBriefCard } from "@/components/research/sector-brief-card";
import type { components } from "@/lib/api";

type SectorBriefPublic = components["schemas"]["SectorBriefPublic"];

const SECTOR_CHUNK_ID = "00000000-0000-4000-8000-0000000000cc";
const SECTOR_THEME_EVIDENCE_ID_1 = "00000000-0000-4000-8000-0000000000d1";
const SECTOR_THEME_EVIDENCE_ID_2 = "00000000-0000-4000-8000-0000000000d2";
const SECTOR_WATCH_EVIDENCE_ID_1 = "00000000-0000-4000-8000-0000000000e1";
const SECTOR_WATCH_EVIDENCE_ID_2 = "00000000-0000-4000-8000-0000000000e2";
const SECTOR_COMPANY_EVIDENCE_ID_1 = "00000000-0000-4000-8000-0000000000f1";
const SECTOR_COMPANY_EVIDENCE_ID_2 = "00000000-0000-4000-8000-0000000000f2";

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

  it("omits the cited claims section when there are no claims", () => {
    render(<SectorBriefCard sectorBrief={makeSectorBrief()} />);
    expect(
      screen.queryByTestId("sector-cited-claim-row"),
    ).not.toBeInTheDocument();
  });

  it("collapses each cited claim by default and expands to show quote, source, and evidence link", () => {
    render(
      <SectorBriefCard
        sectorBrief={makeSectorBrief({
          cited_claims: [
            {
              claim_text: "Hyperscaler capex remains strong.",
              exact_quote: "Capex guidance was raised across the board.",
              chunk_id: SECTOR_CHUNK_ID,
              source: "10-Q",
            },
          ],
        })}
      />,
    );
    const row = screen.getByTestId("sector-cited-claim-row");
    const trigger = within(row).getByRole("button");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(
      within(row).queryByTestId("sector-cited-claim-chunk-link"),
    ).not.toBeInTheDocument();

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(
      within(row).getByText(/Capex guidance was raised across the board\./),
    ).toBeInTheDocument();
    expect(within(row).getByText("10-Q")).toBeInTheDocument();

    const link = within(row).getByTestId("sector-cited-claim-chunk-link");
    expect(link).toHaveAttribute(
      "href",
      `/research/evidence/${SECTOR_CHUNK_ID}`,
    );
    expect(link).toHaveTextContent(SECTOR_CHUNK_ID);
  });

  it("expands the theme evidence list into one trace link per evidence_id", () => {
    render(
      <SectorBriefCard
        sectorBrief={makeSectorBrief({
          themes: [
            {
              name: "AI Capex",
              evidence_ids: [
                SECTOR_THEME_EVIDENCE_ID_1,
                SECTOR_THEME_EVIDENCE_ID_2,
              ],
              confidence: 0.8,
            },
          ],
        })}
      />,
    );
    const row = screen.getByTestId("sector-theme-row");
    const trigger = within(row).getByRole("button");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(
      within(row).queryByTestId("sector-theme-evidence-link"),
    ).not.toBeInTheDocument();

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const links = within(row).getAllByTestId("sector-theme-evidence-link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${SECTOR_THEME_EVIDENCE_ID_1}`,
    );
    expect(links[0]).toHaveTextContent(SECTOR_THEME_EVIDENCE_ID_1);
    expect(links[1]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${SECTOR_THEME_EVIDENCE_ID_2}`,
    );
    expect(links[1]).toHaveTextContent(SECTOR_THEME_EVIDENCE_ID_2);
  });

  it("expands the watch item evidence list into one trace link per evidence_id", () => {
    render(
      <SectorBriefCard
        sectorBrief={makeSectorBrief({
          watch_items: [
            {
              name: "Hyperscaler capex guidance",
              reason: "Next earnings cycle.",
              evidence_ids: [
                SECTOR_WATCH_EVIDENCE_ID_1,
                SECTOR_WATCH_EVIDENCE_ID_2,
              ],
            },
          ],
        })}
      />,
    );
    const row = screen.getByTestId("sector-watch-item-row");
    const trigger = within(row).getByRole("button");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(
      within(row).queryByTestId("sector-watch-item-evidence-link"),
    ).not.toBeInTheDocument();

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const links = within(row).getAllByTestId("sector-watch-item-evidence-link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${SECTOR_WATCH_EVIDENCE_ID_1}`,
    );
    expect(links[0]).toHaveTextContent(SECTOR_WATCH_EVIDENCE_ID_1);
    expect(links[1]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${SECTOR_WATCH_EVIDENCE_ID_2}`,
    );
    expect(links[1]).toHaveTextContent(SECTOR_WATCH_EVIDENCE_ID_2);
  });

  it("expands the company idea evidence list into one trace link per evidence_id", () => {
    render(
      <SectorBriefCard
        sectorBrief={makeSectorBrief({
          companies: [
            {
              name: "Apple",
              ticker: "AAPL",
              direction: "overweight",
              conviction: 0.8,
              evidence_ids: [
                SECTOR_COMPANY_EVIDENCE_ID_1,
                SECTOR_COMPANY_EVIDENCE_ID_2,
              ],
            },
          ],
        })}
      />,
    );
    const row = screen.getByTestId("sector-company-row");
    const trigger = within(row).getByRole("button");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(
      within(row).queryByTestId("sector-company-evidence-link"),
    ).not.toBeInTheDocument();

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const links = within(row).getAllByTestId("sector-company-evidence-link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${SECTOR_COMPANY_EVIDENCE_ID_1}`,
    );
    expect(links[0]).toHaveTextContent(SECTOR_COMPANY_EVIDENCE_ID_1);
    expect(links[1]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${SECTOR_COMPANY_EVIDENCE_ID_2}`,
    );
    expect(links[1]).toHaveTextContent(SECTOR_COMPANY_EVIDENCE_ID_2);
  });

  it("hides the theme evidence toggle when evidence_ids is empty", () => {
    render(
      <SectorBriefCard
        sectorBrief={makeSectorBrief({
          themes: [
            { name: "AI Capex", evidence_ids: [], confidence: 0.8 },
          ],
        })}
      />,
    );
    const row = screen.getByTestId("sector-theme-row");
    expect(within(row).queryByRole("button")).not.toBeInTheDocument();
  });

  it("hides the watch item evidence toggle when evidence_ids is empty", () => {
    render(
      <SectorBriefCard
        sectorBrief={makeSectorBrief({
          watch_items: [
            {
              name: "Hyperscaler capex guidance",
              reason: "Next earnings cycle.",
              evidence_ids: [],
            },
          ],
        })}
      />,
    );
    const row = screen.getByTestId("sector-watch-item-row");
    expect(within(row).queryByRole("button")).not.toBeInTheDocument();
  });

  it("hides the company evidence toggle when evidence_ids is empty", () => {
    render(<SectorBriefCard sectorBrief={makeSectorBrief()} />);
    const row = screen.getByTestId("sector-company-row");
    expect(within(row).queryByRole("button")).not.toBeInTheDocument();
  });
});
