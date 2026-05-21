import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { EvidenceFlow } from "@/components/research/evidence-flow";
import type { components } from "@/lib/api";

type RunEvidenceFlow = components["schemas"]["RunEvidenceFlow"];

const RUN_ID = "11111111-1111-4111-8111-111111111111";

function makeFlow(
  overrides: Partial<RunEvidenceFlow> = {},
): RunEvidenceFlow {
  return {
    run_id: RUN_ID,
    total_evidence: 3,
    total_chunk_citations: 7,
    total_hypotheses: 2,
    sources: [
      {
        source_id: "22222222-2222-4222-8222-222222222222",
        source_name: "edgar",
        source_kind: "filings",
        reliability_score: 0.95,
        evidence_count: 2,
        chunk_citation_count: 5,
        hypothesis_count: 1,
        top_evidence_ids: [],
      },
      {
        source_id: "33333333-3333-4333-8333-333333333333",
        source_name: "tiingo",
        source_kind: "news",
        reliability_score: 0.4,
        evidence_count: 1,
        chunk_citation_count: 2,
        hypothesis_count: 1,
        top_evidence_ids: [],
      },
    ],
    ...overrides,
  };
}

describe("EvidenceFlow", () => {
  it("renders an empty placeholder when no sources", () => {
    render(<EvidenceFlow flow={null} />);
    expect(
      screen.getByText("No evidence has flowed into this run yet."),
    ).toBeInTheDocument();
  });

  it("renders the totals row", () => {
    render(<EvidenceFlow flow={makeFlow()} />);
    const totals = screen.getByTestId("evidence-flow-totals");
    expect(totals.textContent).toContain("3");
    expect(totals.textContent).toContain("7");
    expect(totals.textContent).toContain("2");
  });

  it("renders per-source rows with reliability formatting", () => {
    render(<EvidenceFlow flow={makeFlow()} />);
    const table = screen.getByTestId("evidence-flow-table");
    expect(table.textContent).toContain("edgar");
    expect(table.textContent).toContain("tiingo");
    expect(table.textContent).toContain("95%");
    expect(table.textContent).toContain("40%");
  });

  it("paints low reliability in danger tone", () => {
    render(<EvidenceFlow flow={makeFlow()} />);
    const low = screen.getByText("40%");
    expect(low.className).toContain("text-danger");
  });

  it("paints high reliability in accent tone", () => {
    render(<EvidenceFlow flow={makeFlow()} />);
    const high = screen.getByText("95%");
    expect(high.className).toContain("text-accent-text");
  });
});
