import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";

type ResearchRunDetail = components["schemas"]["ResearchRunDetail"];
type LlmCallLogPublic = components["schemas"]["LlmCallLogPublic"];
type RunCostLedger = components["schemas"]["RunCostLedger"];
type RunEvidenceFlow = components["schemas"]["RunEvidenceFlow"];
type RunGraph = components["schemas"]["RunGraph"];
type CounterfactualRunSummary =
  components["schemas"]["CounterfactualRunSummary"];
type LeakageRunPublic = components["schemas"]["LeakageRunPublic"];
type MacroBriefPublic = components["schemas"]["MacroBriefPublic"];

const NOT_FOUND_STATUS = 404;
const LLM_CALL_FETCH_LIMIT = 500;
const LEAKAGE_FETCH_LIMIT = 50;

export async function loadRunDetail(
  runId: string,
): Promise<ResearchRunDetail | null> {
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

export async function loadLlmCalls(
  runId: string,
): Promise<readonly LlmCallLogPublic[]> {
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

export async function loadCostLedger(
  runId: string,
): Promise<RunCostLedger | null> {
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

export async function loadEvidenceFlow(
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

export async function loadRunGraph(runId: string): Promise<RunGraph | null> {
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

export async function loadCounterfactuals(
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

export async function loadLeakageRuns(
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

export async function loadMacroBrief(
  runId: string,
): Promise<MacroBriefPublic | null> {
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

export function defaultWeekStart(): string {
  const now = new Date();
  const day = now.getUTCDay();
  const diff = (day + 6) % 7;
  const monday = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - diff),
  );
  return monday.toISOString().slice(0, 10);
}
