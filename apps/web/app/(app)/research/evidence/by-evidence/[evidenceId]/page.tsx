import type { Metadata } from "next";
import type { ReactElement } from "react";
import { notFound } from "next/navigation";

import { HexPill } from "@/components/ui";
import { EvidenceTraceDetail } from "@/components/research/evidence-trace-detail";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";

export const metadata: Metadata = {
  title: "Evidence Trace · Alphora",
};

export const dynamic = "force-dynamic";

type EvidenceTracePublic = components["schemas"]["EvidenceTracePublic"];

interface EvidenceTracePageProps {
  params: Promise<{ evidenceId: string }>;
  searchParams?: Promise<{ run_id?: string }>;
}

const NOT_FOUND_STATUS = 404;

async function loadEvidenceTrace(
  evidenceId: string,
  runId: string | undefined,
): Promise<EvidenceTracePublic | null> {
  try {
    const response = await getServerApi().GET(
      "/api/research/evidence/by-evidence/{evidence_id}",
      {
        params: {
          path: { evidence_id: evidenceId },
          query: runId !== undefined ? { run_id: runId } : {},
        },
      },
    );
    if (response.data === undefined) {
      return null;
    }
    return response.data;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

export default async function EvidenceTraceByEvidencePage(
  props: EvidenceTracePageProps,
): Promise<ReactElement> {
  const { evidenceId } = await props.params;
  const search = props.searchParams ? await props.searchParams : undefined;
  const trace = await loadEvidenceTrace(evidenceId, search?.run_id);
  if (trace === null) {
    notFound();
  }
  const providerLabel = trace.data_source?.name ?? trace.evidence.source;

  return (
    <div className="max-w-[1400px] mx-auto">
      <header className="sticky top-0 z-10 bg-canvas border-b border-line">
        <div className="flex items-center gap-4 px-6 py-4">
          <span className="text-2xl font-mono tabular-nums text-fg">
            EVIDENCE TRACE
          </span>
          <HexPill value={trace.evidence.id} />
          <span
            className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted"
            data-testid="evidence-source-label"
          >
            {providerLabel}
          </span>
        </div>
      </header>

      <div className="px-6 pt-4 pb-12">
        <EvidenceTraceDetail data={trace} />
      </div>
    </div>
  );
}
