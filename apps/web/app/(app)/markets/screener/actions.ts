"use server";

import { redirect } from "next/navigation";

import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { formDataToWeights } from "@/lib/screener/parse-weights";

type ScreenerUniverse = components["schemas"]["ScreenerUniverseEnum"];

const SCREENER_LIMIT = 50;
const UNIVERSE_FIELD = "universe";
const ALLOWED_UNIVERSES: readonly ScreenerUniverse[] = [
  "sp500",
  "nasdaq100",
  "watchlist",
] as const;

export interface RunScreenerActionState {
  status: "idle" | "error";
  message: string | null;
  fields: Readonly<Record<string, readonly string[]>>;
}

export const initialRunScreenerState: RunScreenerActionState = {
  status: "idle",
  message: null,
  fields: {},
};

function isAllowedUniverse(value: string): value is ScreenerUniverse {
  return (ALLOWED_UNIVERSES as readonly string[]).includes(value);
}

function normalizeFields(
  raw: Readonly<Record<string, ReadonlyArray<string>>>,
): Readonly<Record<string, readonly string[]>> {
  const out: Record<string, readonly string[]> = {};
  for (const [key, messages] of Object.entries(raw)) {
    out[key] = [...messages];
  }
  return out;
}

export async function runScreener(
  _previousState: RunScreenerActionState,
  formData: FormData,
): Promise<RunScreenerActionState> {
  const rawUniverse = formData.get(UNIVERSE_FIELD);
  if (typeof rawUniverse !== "string" || !isAllowedUniverse(rawUniverse)) {
    return {
      status: "error",
      message: "Select a universe before running the screener.",
      fields: { universe: ["Invalid universe."] },
    };
  }
  if (rawUniverse === "watchlist") {
    return {
      status: "error",
      message:
        "Watchlist screening requires a watchlist selector — coming soon.",
      fields: {
        universe: ["Pick a watchlist from the Watchlists page first."],
      },
    };
  }

  const factorWeights = formDataToWeights(formData);

  let screenerRunId: string;
  try {
    const response = await getServerApi().POST("/api/screeners/run", {
      body: {
        universe: rawUniverse,
        factor_weights: factorWeights,
        limit: SCREENER_LIMIT,
      },
    });
    const created = response.data;
    if (created === undefined) {
      return {
        status: "error",
        message: "Backend returned no screener run.",
        fields: {},
      };
    }
    screenerRunId = created.screener_run.id;
  } catch (caught) {
    if (isApiError(caught)) {
      return {
        status: "error",
        message: caught.detail,
        fields:
          caught.fields !== undefined ? normalizeFields(caught.fields) : {},
      };
    }
    return {
      status: "error",
      message: "Unable to run screener.",
      fields: {},
    };
  }

  redirect(`/markets/screener?run=${screenerRunId}`);
}
