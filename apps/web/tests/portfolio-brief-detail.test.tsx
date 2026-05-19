import { describe, it, expect } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { PortfolioBriefDetail } from "@/components/research/portfolio-brief-detail";
import type { components } from "@/lib/api";

type PortfolioBriefPublic = components["schemas"]["PortfolioBriefPublic"];

const SECTOR_ID = "00000000-0000-4000-8000-000000000001";
const COMPANY_ID = "00000000-0000-4000-8000-000000000010";
const CHUNK_ID = "00000000-0000-4000-8000-000000000020";
const MACRO_THEME_EVIDENCE_ID_1 = "00000000-0000-4000-8000-000000000031";
const MACRO_THEME_EVIDENCE_ID_2 = "00000000-0000-4000-8000-000000000032";
const MACRO_WATCH_EVIDENCE_ID_1 = "00000000-0000-4000-8000-000000000041";
const MACRO_WATCH_EVIDENCE_ID_2 = "00000000-0000-4000-8000-000000000042";

function makeData(
  overrides: Partial<PortfolioBriefPublic["brief"]> = {},
  judgeOverrides: Partial<PortfolioBriefPublic["judge"]> = {},
): PortfolioBriefPublic {
  return {
    brief: {
      run_id: "00000000-0000-4000-8000-000000000099",
      macro: {
        themes: [{ name: "AI Capex", evidence_ids: [], confidence: 0.8 }],
        watch_items: [
          {
            name: "Inflation surprises",
            reason: "CPI prints have run hotter than consensus.",
            evidence_ids: [],
          },
        ],
        confidence: 0.7,
        judge_status: "passed",
      },
      sectors: [
        {
          sector_entity_id: SECTOR_ID,
          sector_name: "Information Technology",
          direction: "overweight",
          conviction: 0.85,
          verifier_status: "verified",
          judge_status: "passed",
          rank: 1,
        },
      ],
      companies: [
        {
          company_entity_id: COMPANY_ID,
          company_name: "Apple",
          ticker: "AAPL",
          sector_entity_id: SECTOR_ID,
          sector_name: "Information Technology",
          direction: "overweight",
          conviction: 0.78,
          verifier_status: "verified",
          judge_status: "passed",
          rank: 1,
        },
      ],
      cited_claims: [
        {
          claim_text: "AI capex remains a multi-year tailwind.",
          exact_quote: "AI capex is forecast to grow 30% in 2026.",
          chunk_id: CHUNK_ID,
          source: "10-Q",
        },
      ],
      cited_chunk_ids: [CHUNK_ID],
      coverage: {
        sectors_selected: 4,
        sectors_verified: 3,
        sectors_judge_passed: 2,
        sectors_judge_flagged: 1,
        companies_selected: 12,
        companies_verified: 10,
        companies_judge_passed: 9,
        companies_judge_flagged: 1,
      },
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

describe("PortfolioBriefDetail", () => {
  it("renders coverage, sector table, company table, and judge badge", () => {
    render(<PortfolioBriefDetail data={makeData()} />);

    const coverage = screen.getByTestId("coverage-grid");
    expect(within(coverage).getByText("SECTORS")).toBeInTheDocument();
    expect(within(coverage).getByText("COMPANIES")).toBeInTheDocument();
    expect(within(coverage).getByText("4")).toBeInTheDocument();
    expect(within(coverage).getByText("12")).toBeInTheDocument();

    const sectorTable = screen.getByTestId("sector-table");
    expect(
      within(sectorTable).getByText("Information Technology"),
    ).toBeInTheDocument();

    const companyTable = screen.getByTestId("company-table");
    expect(within(companyTable).getByText("Apple")).toBeInTheDocument();
    expect(within(companyTable).getByText("AAPL")).toBeInTheDocument();

    expect(screen.getByTestId("judge-badge")).toHaveTextContent(/passed/i);
    expect(screen.getByText("AI Capex")).toBeInTheDocument();
    expect(screen.getByText("Inflation surprises")).toBeInTheDocument();
  });

  it("renders the not_run judge status", () => {
    render(
      <PortfolioBriefDetail
        data={makeData({}, { status: "not_run", reasons: [], call_id: null })}
      />,
    );
    expect(screen.getByTestId("judge-badge")).toHaveTextContent(/not run/i);
  });

  it("renders empty states for sectors, companies, and claims", () => {
    render(
      <PortfolioBriefDetail
        data={makeData({ sectors: [], companies: [], cited_claims: [] })}
      />,
    );
    expect(screen.queryByTestId("sector-table")).not.toBeInTheDocument();
    expect(screen.queryByTestId("company-table")).not.toBeInTheDocument();
    expect(screen.queryByTestId("cited-claim-row")).not.toBeInTheDocument();
    expect(screen.getAllByText("No data.").length).toBeGreaterThanOrEqual(3);
  });

  it("expands cited claim details when the row is clicked", () => {
    render(<PortfolioBriefDetail data={makeData()} />);
    const row = screen.getByTestId("cited-claim-row");
    const trigger = within(row).getByRole("button");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(
      within(row).getByText(/AI capex is forecast to grow 30% in 2026\./),
    ).toBeInTheDocument();
    expect(within(row).getByText(CHUNK_ID)).toBeInTheDocument();
  });

  it("links the expanded cited claim chunk_id to the evidence trace page", () => {
    render(<PortfolioBriefDetail data={makeData()} />);
    const row = screen.getByTestId("cited-claim-row");
    const trigger = within(row).getByRole("button");
    fireEvent.click(trigger);
    const link = within(row).getByTestId("cited-claim-chunk-link");
    expect(link).toHaveAttribute("href", `/research/evidence/${CHUNK_ID}`);
    expect(link).toHaveTextContent(CHUNK_ID);
  });

  it("expands the macro summary theme evidence list into one trace link per evidence_id", () => {
    render(
      <PortfolioBriefDetail
        data={makeData({
          macro: {
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
            watch_items: [],
            confidence: 0.7,
            judge_status: "passed",
          },
        })}
      />,
    );
    const row = screen.getByTestId("portfolio-macro-theme-row");
    const trigger = within(row).getByRole("button");
    fireEvent.click(trigger);
    const links = within(row).getAllByTestId(
      "portfolio-macro-theme-evidence-link",
    );
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute(
      "href",
      `/research/evidence/${MACRO_THEME_EVIDENCE_ID_1}`,
    );
    expect(links[0]).toHaveTextContent(MACRO_THEME_EVIDENCE_ID_1);
    expect(links[1]).toHaveAttribute(
      "href",
      `/research/evidence/${MACRO_THEME_EVIDENCE_ID_2}`,
    );
    expect(links[1]).toHaveTextContent(MACRO_THEME_EVIDENCE_ID_2);
  });

  it("expands the macro summary watch item evidence list into one trace link per evidence_id", () => {
    render(
      <PortfolioBriefDetail
        data={makeData({
          macro: {
            themes: [],
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
            confidence: 0.6,
            judge_status: "passed",
          },
        })}
      />,
    );
    const row = screen.getByTestId("portfolio-macro-watch-item-row");
    const trigger = within(row).getByRole("button");
    fireEvent.click(trigger);
    const links = within(row).getAllByTestId(
      "portfolio-macro-watch-item-evidence-link",
    );
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute(
      "href",
      `/research/evidence/${MACRO_WATCH_EVIDENCE_ID_1}`,
    );
    expect(links[0]).toHaveTextContent(MACRO_WATCH_EVIDENCE_ID_1);
    expect(links[1]).toHaveAttribute(
      "href",
      `/research/evidence/${MACRO_WATCH_EVIDENCE_ID_2}`,
    );
    expect(links[1]).toHaveTextContent(MACRO_WATCH_EVIDENCE_ID_2);
  });
});
