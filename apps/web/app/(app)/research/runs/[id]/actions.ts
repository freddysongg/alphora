"use server";

import { redirect } from "next/navigation";
import { updateTag } from "next/cache";

import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { readNumber, readStringArray } from "@/lib/api/config";

type ConfigDict = Record<string, unknown>;
type LlmProvider = components["schemas"]["LlmProviderEnum"];
type AnalystKind = components["schemas"]["AnalystKindEnum"];
type MacroBriefPublic = components["schemas"]["MacroBriefPublic"];
type PortfolioBriefPublic = components["schemas"]["PortfolioBriefPublic"];

const ALLOWED_PROVIDERS: ReadonlySet<LlmProvider> = new Set<LlmProvider>([
  "openai",
  "anthropic",
  "together",
]);
const ALLOWED_ANALYSTS: ReadonlySet<AnalystKind> = new Set<AnalystKind>([
  "bull",
  "bear",
  "macro",
  "fundamentals",
  "sentiment",
  "risk",
]);
const DEFAULT_PROVIDER: LlmProvider = "openai";
const DEFAULT_MODEL = "gpt-4o-mini";
const DEFAULT_DEBATE_DEPTH = 3;

export interface ActionFailure {
  ok: false;
  error: string;
}

export interface ActionSuccess {
  ok: true;
}

export type ActionResult = ActionSuccess | ActionFailure;

function isLlmProvider(value: unknown): value is LlmProvider {
  return (
    typeof value === "string" &&
    (ALLOWED_PROVIDERS as ReadonlySet<string>).has(value)
  );
}

function filterAnalysts(values: readonly string[]): AnalystKind[] {
  const out: AnalystKind[] = [];
  for (const value of values) {
    if ((ALLOWED_ANALYSTS as ReadonlySet<string>).has(value)) {
      out.push(value as AnalystKind);
    }
  }
  return out;
}

function resolveProvider(config: ConfigDict): LlmProvider {
  const raw = config["llm_provider"];
  if (isLlmProvider(raw)) {
    return raw;
  }
  return DEFAULT_PROVIDER;
}

function resolveModel(config: ConfigDict): string {
  const raw = config["llm_model"];
  if (typeof raw === "string" && raw.length > 0) {
    return raw;
  }
  return DEFAULT_MODEL;
}

function resolveDebateDepth(config: ConfigDict): number {
  const depth = readNumber(config, "debate_depth");
  if (depth === null) {
    return DEFAULT_DEBATE_DEPTH;
  }
  return depth;
}

function resolveAnalysts(config: ConfigDict): AnalystKind[] | undefined {
  const raw = readStringArray(config, "analysts");
  const filtered = filterAnalysts(raw);
  return filtered.length > 0 ? filtered : undefined;
}

export async function cancelResearchRun(runId: string): Promise<ActionResult> {
  try {
    await getServerApi().POST("/api/research-runs/{run_id}/cancel", {
      params: { path: { run_id: runId } },
    });
  } catch (caught) {
    if (isApiError(caught)) {
      return { ok: false, error: caught.detail };
    }
    return { ok: false, error: "Unable to cancel run." };
  }
  updateTag(`research-run-${runId}`);
  updateTag("research-runs");
  return { ok: true };
}

export async function rerunResearchRun(runId: string): Promise<ActionResult> {
  let detail: components["schemas"]["ResearchRunDetail"];
  try {
    const response = await getServerApi().GET(
      "/api/research-runs/{run_id}",
      {
        params: { path: { run_id: runId } },
      },
    );
    if (response.data === undefined) {
      return { ok: false, error: "Run not found." };
    }
    detail = response.data;
  } catch (caught) {
    if (isApiError(caught)) {
      return { ok: false, error: caught.detail };
    }
    return { ok: false, error: "Unable to fetch source run." };
  }

  if (detail.ticker === null) {
    return {
      ok: false,
      error: "Cannot rerun a run without a ticker.",
    };
  }

  const config = detail.config;
  const analysts = resolveAnalysts(config);
  const body = {
    strategy: "tradingagents" as const,
    tickers: [detail.ticker],
    trade_date: detail.trade_date,
    llm_provider: resolveProvider(config),
    llm_model: resolveModel(config),
    debate_depth: resolveDebateDepth(config),
    ...(analysts !== undefined ? { analysts } : {}),
  };

  let createdId: string;
  try {
    const response = await getServerApi().POST("/api/research-runs", {
      body,
    });
    const created = response.data;
    const firstRun = created?.[0];
    if (firstRun === undefined) {
      return { ok: false, error: "Backend returned no runs." };
    }
    createdId = firstRun.id;
  } catch (caught) {
    if (isApiError(caught)) {
      return { ok: false, error: caught.detail };
    }
    return { ok: false, error: "Unable to create run." };
  }

  updateTag("research-runs");
  redirect(`/research/runs/${createdId}`);
}

export async function getMacroBrief(
  runId: string,
): Promise<MacroBriefPublic | null> {
  try {
    const response = await getServerApi().GET(
      "/api/research-runs/{run_id}/macro-brief",
      {
        params: { path: { run_id: runId } },
      },
    );
    if (response.data === undefined) {
      return null;
    }
    return response.data;
  } catch (caught) {
    if (isApiError(caught) && caught.status === 404) {
      return null;
    }
    throw caught;
  }
}

export async function getPortfolioBrief(
  runId: string,
): Promise<PortfolioBriefPublic | null> {
  try {
    const response = await getServerApi().GET(
      "/api/research-runs/{run_id}/portfolio-brief",
      {
        params: { path: { run_id: runId } },
      },
    );
    if (response.data === undefined) {
      return null;
    }
    return response.data;
  } catch (caught) {
    if (isApiError(caught) && caught.status === 404) {
      return null;
    }
    throw caught;
  }
}
