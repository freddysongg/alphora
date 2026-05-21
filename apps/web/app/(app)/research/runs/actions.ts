"use server";

import { updateTag } from "next/cache";

import { getServerApi, isApiError } from "@/lib/api";

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const DEFAULT_DEBATE_DEPTH = 3;

export interface CreateMacroBriefRunInput {
  tradeDate: string;
}

export interface CreateMacroBriefRunSuccess {
  ok: true;
  runId: string;
}

export interface CreateMacroBriefRunFailure {
  ok: false;
  error: string;
}

export type CreateMacroBriefRunResult =
  | CreateMacroBriefRunSuccess
  | CreateMacroBriefRunFailure;

export async function createMacroBriefRun(
  input: CreateMacroBriefRunInput,
): Promise<CreateMacroBriefRunResult> {
  const { tradeDate } = input;
  if (!ISO_DATE_PATTERN.test(tradeDate)) {
    return { ok: false, error: "Trade date must be YYYY-MM-DD." };
  }

  let createdId: string;
  try {
    const response = await getServerApi().POST("/api/research-runs", {
      body: {
        strategy: "funnel_research",
        trade_date: tradeDate,
        scope_payload: { kind: "macro", universe: "us_equities" },
        debate_depth: DEFAULT_DEBATE_DEPTH,
      },
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
    return { ok: false, error: "Unable to create macro brief run." };
  }

  updateTag("research-runs");
  return { ok: true, runId: createdId };
}
