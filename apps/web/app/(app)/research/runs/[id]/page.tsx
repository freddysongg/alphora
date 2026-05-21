import type { Metadata } from "next";
import type { ReactElement } from "react";
import { notFound } from "next/navigation";

import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import type {
  BudgetAction,
  CostMeterState,
} from "@/components/research/live-cost-strip";
import type { InlineClaim } from "@/components/research/inline-claim-review";
import type { SourceClientCacheStats } from "@/components/research/cost-ledger";
import { getMacroBrief, getPortfolioBrief } from "./actions";
import { RunDetail } from "./run-detail";
import type { HypothesisBeliefBundle } from "@/components/research/hypothesis-belief-explainer";
import type { HypothesisLifecycleBundle } from "@/components/research/hypothesis-lifecycle-card";

type HumanReviewSummary = components["schemas"]["HumanReviewSummary"];
type HypothesisPublic = components["schemas"]["HypothesisPublic"];
type BeliefRecomputationPublic =
  components["schemas"]["BeliefRecomputationPublic"];
type HypothesisLifecycleResponse =
  components["schemas"]["HypothesisLifecycleResponse"];
type RunCostEstimate = components["schemas"]["RunCostEstimate"];
type RunCostLedger = components["schemas"]["RunCostLedger"];
type RunEvidenceFlow = components["schemas"]["RunEvidenceFlow"];
type RunGraph = components["schemas"]["RunGraph"];
type CounterfactualRunSummary =
  components["schemas"]["CounterfactualRunSummary"];
type LeakageRunPublic = components["schemas"]["LeakageRunPublic"];
type MacroBriefPublic = components["schemas"]["MacroBriefPublic"];
type CitedClaim = components["schemas"]["CitedClaim"];

export const metadata: Metadata = {
  title: "Run Detail · Alphora",
};

export const dynamic = "force-dynamic";

type ResearchRunDetail = components["schemas"]["ResearchRunDetail"];
type LlmCallLogPublic = components["schemas"]["LlmCallLogPublic"];

interface RunDetailPageProps {
  params: Promise<{ id: string }>;
}

interface InitialCostBundle {
  state: CostMeterState;
  seenLogIds: readonly string[];
  llmCalls: readonly LlmCallLogPublic[];
}

const NOT_FOUND_STATUS = 404;
const INITIAL_LLM_CALL_FETCH_LIMIT = 500;
const LEAKAGE_FETCH_LIMIT = 50;
const INLINE_CLAIM_LIMIT = 20;
const KNOWN_BUDGET_ACTIONS: readonly BudgetAction[] = [
  "allow",
  "warn",
  "pause",
  "kill",
];

function isBudgetAction(value: unknown): value is BudgetAction {
  return (
    typeof value === "string" &&
    (KNOWN_BUDGET_ACTIONS as readonly string[]).includes(value)
  );
}

async function loadRunDetail(runId: string): Promise<ResearchRunDetail | null> {
  try {
    const { data } = await getServerApi().GET("/api/research-runs/{run_id}", {
      params: { path: { run_id: runId } },
      cache: "no-store",
    });
    if (data === undefined) {
      return null;
    }
    return data;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

async function loadInitialCostBundle(
  runId: string,
): Promise<InitialCostBundle> {
  const emptyState: CostMeterState = {
    cumulativeCostUsd: 0,
    inputTokensTotal: 0,
    cachedInputTokensTotal: 0,
    lastModel: null,
    lastBudgetAction: null,
  };
  const empty: InitialCostBundle = {
    state: emptyState,
    seenLogIds: [],
    llmCalls: [],
  };
  try {
    const { data } = await getServerApi().GET(
      "/api/research-runs/{run_id}/llm-calls",
      {
        params: {
          path: { run_id: runId },
          query: { limit: INITIAL_LLM_CALL_FETCH_LIMIT, offset: 0 },
        },
        cache: "no-store",
      },
    );
    if (data === undefined) {
      return empty;
    }
    return aggregateLlmCalls(data);
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return empty;
    }
    throw caught;
  }
}

function aggregateLlmCalls(rows: LlmCallLogPublic[]): InitialCostBundle {
  let cumulativeCostUsd = 0;
  let inputTokensTotal = 0;
  let cachedInputTokensTotal = 0;
  let lastModel: string | null = null;
  let lastBudgetAction: BudgetAction | null = null;
  const seenLogIds: string[] = [];
  const ordered = [...rows].sort(byCreatedAtAscending);
  for (const row of ordered) {
    const parsedCost = Number(row.cost_usd);
    if (Number.isFinite(parsedCost)) {
      cumulativeCostUsd += parsedCost;
    }
    inputTokensTotal += row.input_tokens;
    cachedInputTokensTotal += row.cached_input_tokens;
    lastModel = row.model;
    if (isBudgetAction(row.budget_action)) {
      lastBudgetAction = row.budget_action;
    }
    seenLogIds.push(row.id);
  }
  return {
    state: {
      cumulativeCostUsd,
      inputTokensTotal,
      cachedInputTokensTotal,
      lastModel,
      lastBudgetAction,
    },
    seenLogIds,
    llmCalls: ordered,
  };
}

function byCreatedAtAscending(
  a: LlmCallLogPublic,
  b: LlmCallLogPublic,
): number {
  return a.created_at.localeCompare(b.created_at);
}

async function loadHypothesisBeliefBundles(runId: string): Promise<{
  beliefBundles: readonly HypothesisBeliefBundle[];
  lifecycleBundles: readonly HypothesisLifecycleBundle[];
}> {
  const hypotheses = await loadHypothesesForRun(runId);
  if (hypotheses.length === 0) {
    return { beliefBundles: [], lifecycleBundles: [] };
  }
  const beliefBundles = await Promise.all(
    hypotheses.map(async (hypothesis) => {
      const latest = await loadLatestBelief(hypothesis.id);
      return { hypothesis, latest };
    }),
  );
  const lifecycleBundles = await Promise.all(
    hypotheses.map(async (hypothesis) => {
      const lifecycle = await loadHypothesisLifecycle(hypothesis.id);
      return { hypothesis, lifecycle };
    }),
  );
  return { beliefBundles, lifecycleBundles };
}

async function loadHypothesesForRun(
  runId: string,
): Promise<readonly HypothesisPublic[]> {
  try {
    const { data } = await getServerApi().GET("/api/research/hypotheses", {
      params: { query: { run_id: runId, limit: 100 } },
      cache: "no-store",
    });
    return data?.items ?? [];
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return [];
    }
    throw caught;
  }
}

async function loadLatestBelief(
  hypothesisId: string,
): Promise<BeliefRecomputationPublic | null> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research/hypotheses/{hypothesis_id}/belief",
      {
        params: { path: { hypothesis_id: hypothesisId } },
        cache: "no-store",
      },
    );
    return data?.latest ?? null;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

async function loadHypothesisLifecycle(
  hypothesisId: string,
): Promise<HypothesisLifecycleResponse | null> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research/hypotheses/{hypothesis_id}/lifecycle",
      {
        params: { path: { hypothesis_id: hypothesisId } },
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

async function loadCostEstimate(
  strategy: ResearchRunDetail["strategy"],
): Promise<RunCostEstimate | null> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research-runs/cost-estimate",
      {
        params: { query: { strategy } },
        cache: "no-store",
      },
    );
    return data ?? null;
  } catch {
    return null;
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

async function loadEvidenceFlow(
  runId: string,
): Promise<RunEvidenceFlow | null> {
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

async function loadHumanReviewSummary(): Promise<HumanReviewSummary> {
  try {
    const { data } = await getServerApi().GET("/api/human-reviews/summary", {
      params: { query: { weeks: 8 } },
      cache: "no-store",
    });
    return data ?? { weeks: [] };
  } catch {
    return { weeks: [] };
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

export default async function RunDetailPage(
  props: RunDetailPageProps,
): Promise<ReactElement> {
  const { id } = await props.params;
  const detail = await loadRunDetail(id);
  if (detail === null) {
    notFound();
  }
  const isFunnel = detail.strategy === "funnel_research";
  const [
    macroBrief,
    portfolioBrief,
    initialCost,
    costEstimate,
    reviewSummary,
    hypothesisBundles,
    costLedger,
    evidenceFlow,
    runGraph,
    counterfactuals,
    leakageRuns,
  ] = await Promise.all([
    isFunnel ? getMacroBrief(id) : Promise.resolve(null),
    isFunnel ? getPortfolioBrief(id) : Promise.resolve(null),
    loadInitialCostBundle(id),
    loadCostEstimate(detail.strategy),
    loadHumanReviewSummary(),
    loadHypothesisBeliefBundles(id),
    loadCostLedger(id),
    loadEvidenceFlow(id),
    loadRunGraph(id),
    loadCounterfactuals(id),
    loadLeakageRuns(id),
  ]);
  const sourceClientCacheStats =
    (detail.source_client_cache_stats as
      | SourceClientCacheStats
      | null
      | undefined) ?? null;
  const claims = projectClaims(macroBrief);
  return (
    <RunDetail
      detail={detail}
      macroBrief={macroBrief}
      portfolioBrief={portfolioBrief}
      initialCostState={initialCost.state}
      initialSeenLogIds={initialCost.seenLogIds}
      costEstimate={costEstimate}
      humanReviewSummary={reviewSummary}
      defaultWeekStart={defaultWeekStart()}
      beliefBundles={hypothesisBundles.beliefBundles}
      lifecycleBundles={hypothesisBundles.lifecycleBundles}
      llmCalls={initialCost.llmCalls}
      costLedger={costLedger}
      evidenceFlow={evidenceFlow}
      runGraph={runGraph}
      counterfactuals={counterfactuals}
      leakage={leakageRuns}
      claims={claims}
      sourceClientCacheStats={sourceClientCacheStats}
    />
  );
}
