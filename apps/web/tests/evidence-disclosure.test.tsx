import { describe, it, expect } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";

import { useEvidenceDisclosure } from "@/components/research/evidence-disclosure";

const EVIDENCE_ID_1 = "00000000-0000-4000-8000-000000000001";
const EVIDENCE_ID_2 = "00000000-0000-4000-8000-000000000002";

interface HarnessProps {
  ids: readonly string[];
  testIdPrefix: string;
  runId?: string;
}

function Harness(props: HarnessProps): ReactElement {
  const { ids, testIdPrefix, runId } = props;
  const { button, list, hasEvidence } = useEvidenceDisclosure(
    ids,
    testIdPrefix,
    runId,
  );
  return (
    <div data-testid="harness">
      <span data-testid="has-evidence-flag">{String(hasEvidence)}</span>
      <div data-testid="button-slot">{button}</div>
      <div data-testid="list-slot">{list}</div>
    </div>
  );
}

describe("useEvidenceDisclosure", () => {
  it("returns hasEvidence=false and null button/list when ids is empty", () => {
    render(<Harness ids={[]} testIdPrefix="test" />);
    expect(screen.getByTestId("has-evidence-flag")).toHaveTextContent("false");
    expect(screen.getByTestId("button-slot").children).toHaveLength(0);
    expect(screen.getByTestId("list-slot").children).toHaveLength(0);
  });

  it("renders an 'Evidence N' button collapsed by default with hasEvidence=true", () => {
    render(
      <Harness ids={[EVIDENCE_ID_1, EVIDENCE_ID_2]} testIdPrefix="test" />,
    );
    expect(screen.getByTestId("has-evidence-flag")).toHaveTextContent("true");
    const button = within(screen.getByTestId("button-slot")).getByRole(
      "button",
    );
    expect(button).toHaveTextContent("Evidence 2");
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("list-slot").children).toHaveLength(0);
  });

  it("expands to one trace link per id when toggled", () => {
    render(
      <Harness ids={[EVIDENCE_ID_1, EVIDENCE_ID_2]} testIdPrefix="test" />,
    );
    const button = within(screen.getByTestId("button-slot")).getByRole(
      "button",
    );
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    const links = within(screen.getByTestId("list-slot")).getAllByTestId(
      "test-evidence-link",
    );
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${EVIDENCE_ID_1}`,
    );
    expect(links[0]).toHaveTextContent(EVIDENCE_ID_1);
    expect(links[1]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${EVIDENCE_ID_2}`,
    );
    expect(links[1]).toHaveTextContent(EVIDENCE_ID_2);
  });

  it("collapses the list when toggled a second time", () => {
    render(<Harness ids={[EVIDENCE_ID_1]} testIdPrefix="test" />);
    const button = within(screen.getByTestId("button-slot")).getByRole(
      "button",
    );
    fireEvent.click(button);
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("list-slot").children).toHaveLength(0);
  });

  it("appends ?run_id when runId is provided so the trace endpoint scopes citations to that run", () => {
    const runId = "11111111-1111-4111-8111-111111111111";
    render(
      <Harness
        ids={[EVIDENCE_ID_1, EVIDENCE_ID_2]}
        testIdPrefix="scoped"
        runId={runId}
      />,
    );
    fireEvent.click(
      within(screen.getByTestId("button-slot")).getByRole("button"),
    );
    const links = within(screen.getByTestId("list-slot")).getAllByTestId(
      "scoped-evidence-link",
    );
    expect(links[0]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${EVIDENCE_ID_1}?run_id=${runId}`,
    );
    expect(links[1]).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${EVIDENCE_ID_2}?run_id=${runId}`,
    );
  });

  it("omits the run_id query when runId is undefined", () => {
    render(<Harness ids={[EVIDENCE_ID_1]} testIdPrefix="unscoped" />);
    fireEvent.click(
      within(screen.getByTestId("button-slot")).getByRole("button"),
    );
    const link = within(screen.getByTestId("list-slot")).getByTestId(
      "unscoped-evidence-link",
    );
    expect(link).toHaveAttribute(
      "href",
      `/research/evidence/by-evidence/${EVIDENCE_ID_1}`,
    );
  });

  it("uses the provided prefix for each link's data-testid", () => {
    render(
      <Harness ids={[EVIDENCE_ID_1]} testIdPrefix="my-custom-row" />,
    );
    fireEvent.click(
      within(screen.getByTestId("button-slot")).getByRole("button"),
    );
    expect(
      within(screen.getByTestId("list-slot")).getByTestId(
        "my-custom-row-evidence-link",
      ),
    ).toBeInTheDocument();
  });
});
