import type { Metadata } from "next";
import type { ReactElement } from "react";
import { notFound } from "next/navigation";

import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import type {
  BudgetAction,
  CostMeterState,
} from "@/components/research/run-cost-meter";
import { getMacroBrief } from "./actions";
import { RunDetail } from "./run-detail";

type CounterfactualRunSummary =
  components["schemas"]["CounterfactualRunSummary"];
type HumanReviewSummary = components["schemas"]["HumanReviewSummary"];
type HypothesisPublic = components["schemas"]["HypothesisPublic"];
type BeliefRecomputationPublic =
  components["schemas"]["BeliefRecomputationPublic"];
import type { HypothesisBeliefBundle } from "@/components/research/hypothesis-belief-explainer";

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
}

const NOT_FOUND_STATUS = 404;
const INITIAL_LLM_CALL_FETCH_LIMIT = 500;
const KNOWN_BUDGET_ACTIONS: readonly BudgetAction[] = [
  "allow",
  "warn",
  "pause",
  "kill",
];

function isBudgetAction(value: unknown): value is BudgetAction {
  return typeof value === "string"
    && (KNOWN_BUDGET_ACTIONS as readonly string[]).includes(value);
}

async function loadRunDetail(
  runId: string,
): Promise<ResearchRunDetail | null> {
  try {
    const { data } = await getServerApi().GET("/api/research-runs/{run_id}", {
      params: { path: { run_id: runId } },
      cache: "force-cache",
      next: { tags: ["research-runs", `research-run-${runId}`] },
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

async function loadInitialCostBundle(runId: string): Promise<InitialCostBundle> {
  const emptyState: CostMeterState = {
    cumulativeCostUsd: 0,
    inputTokensTotal: 0,
    cachedInputTokensTotal: 0,
    lastModel: null,
    lastBudgetAction: null,
  };
  const empty: InitialCostBundle = { state: emptyState, seenLogIds: [] };
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
  };
}

function byCreatedAtAscending(
  a: LlmCallLogPublic,
  b: LlmCallLogPublic,
): number {
  return a.created_at.localeCompare(b.created_at);
}

async function loadCounterfactualSummary(
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

async function loadHypothesisBeliefBundles(
  runId: string,
): Promise<readonly HypothesisBeliefBundle[]> {
  const hypotheses = await loadHypothesesForRun(runId);
  if (hypotheses.length === 0) {
    return [];
  }
  const bundles = await Promise.all(
    hypotheses.map(async (hypothesis) => {
      const latest = await loadLatestBelief(hypothesis.id);
      return { hypothesis, latest };
    }),
  );
  return bundles;
}

async function loadHypothesesForRun(
  runId: string,
): Promise<readonly HypothesisPublic[]> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research/hypotheses",
      {
        params: { query: { run_id: runId, limit: 100 } },
        cache: "no-store",
      },
    );
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
  const macroBrief =
    detail.strategy === "funnel_research" ? await getMacroBrief(id) : null;
  const initialCost = await loadInitialCostBundle(id);
  const counterfactuals = await loadCounterfactualSummary(id);
  const reviewSummary = await loadHumanReviewSummary();
  const beliefBundles = await loadHypothesisBeliefBundles(id);
  return (
    <RunDetail
      detail={detail}
      macroBrief={macroBrief}
      initialCostState={initialCost.state}
      initialSeenLogIds={initialCost.seenLogIds}
      counterfactualGates={counterfactuals?.gates ?? []}
      humanReviewSummary={reviewSummary}
      defaultWeekStart={defaultWeekStart()}
      beliefBundles={beliefBundles}
    />
  );
}
