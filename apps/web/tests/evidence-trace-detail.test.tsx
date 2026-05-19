import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { EvidenceTraceDetail } from "@/components/research/evidence-trace-detail";
import type { components } from "@/lib/api";

type EvidenceTracePublic = components["schemas"]["EvidenceTracePublic"];
type EvidenceChunkPublic = components["schemas"]["EvidenceChunkPublic"];

const EVIDENCE_ID = "00000000-0000-4000-8000-000000000001";
const SOURCE_ID = "00000000-0000-4000-8000-000000000002";
const CHUNK_ID_0 = "00000000-0000-4000-8000-000000000010";
const CHUNK_ID_1 = "00000000-0000-4000-8000-000000000011";
const CHUNK_ID_2 = "00000000-0000-4000-8000-000000000012";

function makeChunk(
  overrides: Partial<EvidenceChunkPublic> = {},
): EvidenceChunkPublic {
  return {
    id: CHUNK_ID_1,
    evidence_id: EVIDENCE_ID,
    chunk_index: 1,
    text: "Selected chunk body.",
    start_offset: null,
    end_offset: null,
    attributes: null,
    content_hash: "a".repeat(64),
    created_at: "2026-05-19T12:00:00Z",
    ...overrides,
  };
}

function makeData(
  overrides: Partial<EvidenceTracePublic> = {},
): EvidenceTracePublic {
  const selected = makeChunk();
  return {
    chunk: selected,
    evidence: {
      id: EVIDENCE_ID,
      source: "edgar",
      source_id: SOURCE_ID,
      document_id: "doc-42",
      raw_url: "https://example.com/raw/doc-42",
      raw_blob_ref: null,
      content_hash: "b".repeat(64),
      structured: null,
      extracted_at: "2026-05-19T12:00:00Z",
      extracted_by_model: "gpt-test",
      prompt_version: "v3",
      sign: 1,
      created_at: "2026-05-19T11:59:00Z",
      updated_at: "2026-05-19T12:01:00Z",
    },
    data_source: {
      id: SOURCE_ID,
      name: "edgar",
      kind: "filings",
      description: "SEC EDGAR public filings",
      homepage_url: "https://www.sec.gov",
      attributes: null,
      created_at: "2026-05-19T10:00:00Z",
      updated_at: "2026-05-19T10:00:00Z",
    },
    context_chunks: [
      makeChunk({
        id: CHUNK_ID_0,
        chunk_index: 0,
        text: "Preceding chunk body.",
      }),
      selected,
      makeChunk({
        id: CHUNK_ID_2,
        chunk_index: 2,
        text: "Following chunk body.",
      }),
    ],
    ...overrides,
  };
}

describe("EvidenceTraceDetail", () => {
  it("renders selected chunk, context chunks, source metadata, and raw URL link", () => {
    render(<EvidenceTraceDetail data={makeData()} />);

    expect(screen.getByTestId("selected-chunk-text")).toHaveTextContent(
      "Selected chunk body.",
    );

    const contextChunks = screen.getAllByTestId("evidence-context-chunk");
    expect(contextChunks).toHaveLength(3);
    expect(contextChunks[0]).toHaveTextContent("Preceding chunk body.");
    expect(contextChunks[1]).toHaveTextContent("Selected chunk body.");
    expect(contextChunks[1]).toHaveAttribute("data-selected", "true");
    expect(contextChunks[2]).toHaveTextContent("Following chunk body.");

    const evidenceMetadata = screen.getByTestId("evidence-metadata");
    expect(within(evidenceMetadata).getByText("edgar")).toBeInTheDocument();
    expect(within(evidenceMetadata).getByText("doc-42")).toBeInTheDocument();
    expect(within(evidenceMetadata).getByText("gpt-test")).toBeInTheDocument();
    expect(within(evidenceMetadata).getByText("v3")).toBeInTheDocument();

    const rawUrl = screen.getByTestId("evidence-raw-url");
    expect(rawUrl).toHaveAttribute("href", "https://example.com/raw/doc-42");
    expect(rawUrl).toHaveAttribute("target", "_blank");
    expect(rawUrl).toHaveAttribute("rel", "noreferrer noopener");

    const dataSourceMetadata = screen.getByTestId("data-source-metadata");
    expect(
      within(dataSourceMetadata).getByText("SEC EDGAR public filings"),
    ).toBeInTheDocument();
    expect(within(dataSourceMetadata).getByText("filings")).toBeInTheDocument();
  });

  it("renders 'Not recorded' for missing optional metadata", () => {
    render(
      <EvidenceTraceDetail
        data={makeData({
          evidence: {
            ...makeData().evidence,
            raw_url: null,
            extracted_by_model: null,
            prompt_version: null,
          },
          data_source: null,
        })}
      />,
    );

    expect(screen.queryByTestId("evidence-raw-url")).not.toBeInTheDocument();
    expect(screen.queryByTestId("data-source-metadata")).not.toBeInTheDocument();
    expect(screen.getByTestId("data-source-empty")).toHaveTextContent(
      "Not recorded",
    );

    const notRecordedNodes = screen.getAllByText("Not recorded");
    expect(notRecordedNodes.length).toBeGreaterThanOrEqual(4);
  });
});
