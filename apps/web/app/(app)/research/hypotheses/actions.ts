"use server";

import { updateTag } from "next/cache";

import { getServerApi, isApiError } from "@/lib/api";
import { HYPOTHESES_CACHE_TAG } from "./cache-tags";

export interface ActivateHypothesisSuccess {
  ok: true;
}

export interface ActivateHypothesisFailure {
  ok: false;
  error: string;
}

export type ActivateHypothesisResult =
  | ActivateHypothesisSuccess
  | ActivateHypothesisFailure;

export async function activateHypothesis(
  hypothesisId: string,
): Promise<ActivateHypothesisResult> {
  try {
    await getServerApi().POST(
      "/api/research/hypotheses/{hypothesis_id}/activate",
      {
        params: { path: { hypothesis_id: hypothesisId } },
      },
    );
  } catch (caught) {
    if (isApiError(caught)) {
      return { ok: false, error: caught.detail };
    }
    return { ok: false, error: "Unable to activate hypothesis." };
  }

  updateTag(HYPOTHESES_CACHE_TAG);
  return { ok: true };
}
