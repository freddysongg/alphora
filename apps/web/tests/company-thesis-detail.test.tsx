import { describe, it, expect } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { CompanyThesisDetail } from "@/components/research/company-thesis-detail";
import type { components } from "@/lib/api";

type CompanyThesisPublic = components["schemas"]["CompanyThesisPublic"];

const COMPANY_ENTITY_ID = "00000000-0000-4000-8000-000000000001";
const SECTOR_ENTITY_ID = "00000000-0000-4000-8000-000000000002";
const CATALYST_EVIDENCE_ID_1 = "00000000-0000-4000-8000-0000000000a1";
const CATALYST_EVIDENCE_ID_2 = "00000000-0000-4000-8000-0000000000a2";
const RISK_EVIDENCE_ID = "00000000-0000-4000-8000-0000000000b1";
const THESIS_EVIDENCE_ID_1 = "00000000-0000-4000-8000-0000000000c1";
const THESIS_EVIDENCE_ID_2 = "00000000-0000-4000-8000-0000000000c2";
const CITED_CLAIM_CHUNK_ID = "00000000-0000-4000-8000-0000000000d1";

function makeThesis(
  thesisOverrides: Partial<CompanyThesisPublic["thesis"]> = {},
  judgeOverrides: Partial<CompanyThesisPublic["judge"]> = {},
  chunks: CompanyThesisPublic["chunks"] = [],
): CompanyThesisPublic {
  return {
    thesis: {
      company_entity_id: COMPANY_ENTITY_ID,
      company_name: "Apple Inc.",
      sector_entity_id: SECTOR_ENTITY_ID,
      sector_name: "Information Technology",
      ticker: "AAPL",
      direction: "overweight",
      conviction: 0.8,
      bull_case: "Services growth accelerates into 2027.",
      bear_case: "iPhone demand decelerates faster than consensus.",
      catalysts: [],
      risks: [],
      cited_claims: [],
      confidence: 0.7,
      evidence_ids: [],
      verifier_status: "verified",
      regeneration_count: 0,
      ...thesisOverrides,
    },
    judge: {
      status: "passed",
      reasons: [],
      call_id: null,
      ...judgeOverrides,
    },
    chunks,
  };
}

describe("CompanyThesisDetail", () => {
  it("renders company name, ticker, sector, direction, and conviction", () => {
    render(<CompanyThesisDetail data={makeThesis()} />);
    expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("Information Technology")).toBeInTheDocument();
    expect(screen.getByText("overweight")).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
  });

  it("renders the judge badge", () => {
    render(
      <CompanyThesisDetail
        data={makeThesis({}, { status: "flagged" })}
      />,
    );
    expect(screen.getByTestId("judge-badge")).toHaveTextContent(/flagged/i);
  });

  it("renders bull and bear case prose", () => {
    render(<CompanyThesisDetail data={makeThesis()} />);
    expect(
      screen.getByText(/Services growth accelerates into 2027\./),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/iPhone demand decelerates faster than consensus\./),
    ).toBeInTheDocument();
  });

  it("expands a catalyst evidence list into one trace link per evidence_id", () => {
    render(
      <CompanyThesisDetail
        data={makeThesis({
          catalysts: [
            {
              name: "WWDC 2026",
              expected_timing: "Q3 2026",
              evidence_ids: [
                CATALYST_EVIDENCE_ID_1,
                CATALYST_EVIDENCE_ID_2,
              ],
            },
          ],
        })}
      />,
    );
    const row = screen.getByTestId("company-catalyst-row");
    expect(within(row).getByText("WWDC 2026")).toBeInTheDocument();
    expect(within(row).getByText(/Q3 2026/)).toBeInTheDocument();
    const trigger = within(row).getByRole("button");
    fireEvent.click(trigger);
    const links = within(row).getAllByTestId("company-catalyst-evidence-link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${CATALYST_EVIDENCE_ID_1}`,
    );
    expect(links[1]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${CATALYST_EVIDENCE_ID_2}`,
    );
  });

  it("expands a risk evidence list into one trace link per evidence_id and shows severity", () => {
    render(
      <CompanyThesisDetail
        data={makeThesis({
          risks: [
            {
              name: "EU regulatory action",
              severity: 0.6,
              evidence_ids: [RISK_EVIDENCE_ID],
            },
          ],
        })}
      />,
    );
    const row = screen.getByTestId("company-risk-row");
    expect(within(row).getByText("EU regulatory action")).toBeInTheDocument();
    expect(within(row).getByText("0.60")).toBeInTheDocument();
    fireEvent.click(within(row).getByRole("button"));
    const link = within(row).getByTestId("company-risk-evidence-link");
    expect(link).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${RISK_EVIDENCE_ID}`,
    );
  });

  it("expands the top-level thesis evidence list into trace links", () => {
    render(
      <CompanyThesisDetail
        data={makeThesis({
          evidence_ids: [THESIS_EVIDENCE_ID_1, THESIS_EVIDENCE_ID_2],
        })}
      />,
    );
    const row = screen.getByTestId("company-thesis-evidence-row");
    fireEvent.click(within(row).getByRole("button"));
    const links = within(row).getAllByTestId("company-thesis-evidence-link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${THESIS_EVIDENCE_ID_1}`,
    );
    expect(links[1]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${THESIS_EVIDENCE_ID_2}`,
    );
  });

  it("links cited claim chunk_id to the chunk-id trace route", () => {
    render(
      <CompanyThesisDetail
        data={makeThesis({
          cited_claims: [
            {
              claim_text: "Services revenue grew 18% YoY.",
              exact_quote: "Services revenue grew 18% year over year.",
              chunk_id: CITED_CLAIM_CHUNK_ID,
              source: "10-Q",
            },
          ],
        })}
      />,
    );
    const row = screen.getByTestId("company-cited-claim-row");
    fireEvent.click(within(row).getByRole("button"));
    const link = within(row).getByTestId("company-cited-claim-chunk-link");
    expect(link).toHaveAttribute(
      "href",
      `/research/evidence/${CITED_CLAIM_CHUNK_ID}`,
    );
    expect(link).toHaveTextContent(CITED_CLAIM_CHUNK_ID);
  });

  it("hides the catalyst evidence toggle when evidence_ids is empty", () => {
    render(
      <CompanyThesisDetail
        data={makeThesis({
          catalysts: [
            {
              name: "Earnings beat",
              expected_timing: null,
              evidence_ids: [],
            },
          ],
        })}
      />,
    );
    const row = screen.getByTestId("company-catalyst-row");
    expect(within(row).queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders chunk-preview text inside the expanded cited claim row", () => {
    render(
      <CompanyThesisDetail
        data={makeThesis(
          {
            cited_claims: [
              {
                claim_text: "Services revenue grew 18% YoY.",
                exact_quote: "Services revenue grew 18% year over year.",
                chunk_id: CITED_CLAIM_CHUNK_ID,
                source: "10-Q",
              },
            ],
          },
          {},
          [
            {
              chunk_id: CITED_CLAIM_CHUNK_ID,
              evidence_id: "00000000-0000-4000-8000-0000000000d2",
              source: "10-Q",
              text: "Services revenue grew 18% year over year as the installed base expanded.",
              attributes: {},
            },
          ],
        )}
      />,
    );
    const row = screen.getByTestId("company-cited-claim-row");
    fireEvent.click(within(row).getByRole("button"));
    expect(
      within(row).getByText(/Services revenue grew 18% year over year\./),
    ).toBeInTheDocument();
    expect(
      within(row).getByText(/installed base expanded/),
    ).toBeInTheDocument();
  });

  it("renders the cited claim chunk link even when the chunk lookup is missing", () => {
    render(
      <CompanyThesisDetail
        data={makeThesis({
          cited_claims: [
            {
              claim_text: "Margin pressure intensifies.",
              exact_quote: "Margins compressed materially.",
              chunk_id: CITED_CLAIM_CHUNK_ID,
              source: "10-K",
            },
          ],
        })}
      />,
    );
    const row = screen.getByTestId("company-cited-claim-row");
    fireEvent.click(within(row).getByRole("button"));
    const link = within(row).getByTestId("company-cited-claim-chunk-link");
    expect(link).toHaveAttribute(
      "href",
      `/research/evidence/${CITED_CLAIM_CHUNK_ID}`,
    );
  });
});
