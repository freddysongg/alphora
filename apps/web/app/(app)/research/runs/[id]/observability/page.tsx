import type { Metadata } from "next";
import type { ReactElement } from "react";
import type { Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, HexPill } from "@/components/ui";
import { CostLedger } from "@/components/research/cost-ledger";
import { CounterfactualMatrix } from "@/components/research/counterfactual-matrix";
import { EvidenceFlow } from "@/components/research/evidence-flow";
import { KnowledgeGraph } from "@/components/research/knowledge-graph";
import { LeakageChart } from "@/components/research/leakage-chart";
import { RunTimelineFlame } from "@/components/research/run-timeline-flame";
import type { InlineClaim } from "@/components/research/inline-claim-review";

import { InlineClaimReviewSection } from "./inline-claim-review-section";

export const metadata: Metadata = {
  title: "Run Observability · Alphora",
};

export const dynamic = "force-dynamic";

type ResearchRunDetail = components["schemas"]["ResearchRunDetail"];
type LlmCallLogPublic = components["schemas"]["LlmCallLogPublic"];
type RunCostLedger = components["schemas"]["RunCostLedger"];
type RunEvidenceFlow = components["schemas"]["RunEvidenceFlow"];
type RunGraph = components["schemas"]["RunGraph"];
type CounterfactualRunSummary =
  components["schemas"]["CounterfactualRunSummary"];
type LeakageRunPublic = components["schemas"]["LeakageRunPublic"];
type MacroBriefPublic = components["schemas"]["MacroBriefPublic"];
type CitedClaim = components["schemas"]["CitedClaim"];

const NOT_FOUND_STATUS = 404;
const LLM_CALL_FETCH_LIMIT = 500;
const LEAKAGE_FETCH_LIMIT = 50;
const INLINE_CLAIM_LIMIT = 20;

interface ObservabilityPageProps {
  params: Promise<{ id: string }>;
}

async function loadRunDetail(runId: string): Promise<ResearchRunDetail | null> {
  try {
    const { data } = await getServerApi().GET("/api/research-runs/{run_id}", {
      params: { path: { run_id: runId } },
      cache: "no-store",
    });
    return data ?? null;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

async function loadLlmCalls(runId: string): Promise<readonly LlmCallLogPublic[]> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research-runs/{run_id}/llm-calls",
      {
        params: {
          path: { run_id: runId },
          query: { limit: LLM_CALL_FETCH_LIMIT, offset: 0 },
        },
        cache: "no-store",
      },
    );
    return data ?? [];
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return [];
    }
    throw caught;
  }
}

async function loadCostLedger(runId: string): Promise<RunCostLedger | null> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research-runs/{run_id}/cost-ledger",
      {
        params: { path: { run_id: runId } },
        cache: "no-store",
      },
    );
    return data ?? null;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

async function loadEvidenceFlow(runId: string): Promise<RunEvidenceFlow | null> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research-runs/{run_id}/evidence-flow",
      {
        params: { path: { run_id: runId } },
        cache: "no-store",
      },
    );
    return data ?? null;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

async function loadRunGraph(runId: string): Promise<RunGraph | null> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research-runs/{run_id}/graph",
      {
        params: { path: { run_id: runId } },
        cache: "no-store",
      },
    );
    return data ?? null;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

async function loadCounterfactuals(
  runId: string,
): Promise<CounterfactualRunSummary | null> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research-runs/{run_id}/counterfactuals",
      {
        params: { path: { run_id: runId } },
        cache: "no-store",
      },
    );
    return data ?? null;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

async function loadLeakageRuns(
  runId: string,
): Promise<readonly LeakageRunPublic[]> {
  try {
    const { data } = await getServerApi().GET("/api/evals/leakage/runs", {
      params: { query: { run_id: runId, limit: LEAKAGE_FETCH_LIMIT } },
      cache: "no-store",
    });
    return data ?? [];
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return [];
    }
    throw caught;
  }
}

async function loadMacroBrief(runId: string): Promise<MacroBriefPublic | null> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research-runs/{run_id}/macro-brief",
      {
        params: { path: { run_id: runId } },
        cache: "no-store",
      },
    );
    return data ?? null;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

function defaultWeekStart(): string {
  const now = new Date();
  const day = now.getUTCDay();
  const diff = (day + 6) % 7;
  const monday = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - diff),
  );
  return monday.toISOString().slice(0, 10);
}

function projectClaims(
  macroBrief: MacroBriefPublic | null,
): readonly InlineClaim[] {
  if (macroBrief === null) {
    return [];
  }
  const seenChunkIds = new Set<string>();
  const projected: InlineClaim[] = [];
  const claims: readonly CitedClaim[] = macroBrief.brief.cited_claims;
  for (const claim of claims) {
    if (seenChunkIds.has(claim.chunk_id)) {
      continue;
    }
    seenChunkIds.add(claim.chunk_id);
    projected.push({
      chunkId: claim.chunk_id,
      quote: claim.exact_quote,
      briefKind: "macro",
      briefId: null,
      source: claim.source,
    });
    if (projected.length >= INLINE_CLAIM_LIMIT) {
      break;
    }
  }
  return projected;
}

export default async function RunObservabilityPage(
  props: ObservabilityPageProps,
): Promise<ReactElement> {
  const { id } = await props.params;
  const detail = await loadRunDetail(id);
  if (detail === null) {
    notFound();
  }
  const [calls, costLedger, evidenceFlow, runGraph, counterfactuals, leakageRuns, macroBrief] =
    await Promise.all([
      loadLlmCalls(id),
      loadCostLedger(id),
      loadEvidenceFlow(id),
      loadRunGraph(id),
      loadCounterfactuals(id),
      loadLeakageRuns(id),
      detail.strategy === "funnel_research" ? loadMacroBrief(id) : Promise.resolve(null),
    ]);
  const inlineClaims = projectClaims(macroBrief);
  return (
    <div className="max-w-[1400px] mx-auto" data-testid="observability-page">
      <header className="sticky top-0 z-10 bg-canvas border-b border-line">
        <div className="flex items-center gap-4 px-6 py-4">
          <Link
            href={`/research/runs/${detail.id}` as Route}
            className="text-sm text-fg-muted hover:text-fg underline-offset-2 hover:underline"
          >
            ← RUN DETAIL
          </Link>
          <span className="text-2xl font-mono tabular-nums text-fg">
            OBSERVABILITY
          </span>
          <HexPill value={detail.id} />
        </div>
      </header>

      <div className="px-6 pt-4 pb-12 flex flex-col gap-6">
        <RunTimelineFlame calls={calls} />
        <CostLedger
          ledger={costLedger}
          sourceClientCacheStats={
            (detail.source_client_cache_stats as
              | { hits?: number; misses?: number; evictions?: number; hit_rate?: number }
              | null
              | undefined) ?? null
          }
        />
        <EvidenceFlow flow={evidenceFlow} />
        <CounterfactualMatrix
          perturbations={counterfactuals?.perturbations ?? []}
        />
        <LeakageChart runs={leakageRuns} />
        <InlineClaimReviewSection
          runId={detail.id}
          defaultWeekStart={defaultWeekStart()}
          claims={inlineClaims}
        />
        <KnowledgeGraph graph={runGraph} />
        {inlineClaims.length === 0 && macroBrief === null ? (
          <Card>
            <CardHeader>
              <CardTitle>NO MACRO BRIEF</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-fg-subtle">
                Inline claim review is empty because this run has no macro brief yet.
              </p>
            </CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
