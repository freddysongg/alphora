"use server";

import { redirect } from "next/navigation";
import { updateTag } from "next/cache";

import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";

type LlmProvider = components["schemas"]["LlmProviderEnum"];

const DEFAULT_PROVIDER: LlmProvider = "openai";
const DEFAULT_MODEL = "gpt-4o-mini";
const DEFAULT_DEBATE_DEPTH = 3;
const TICKER_MAX_LENGTH = 16;
const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export interface NewRunFieldErrors {
  ticker?: readonly string[];
  trade_date?: readonly string[];
}

export interface NewRunActionState {
  status: "idle" | "error";
  message: string | null;
  fields: NewRunFieldErrors;
}

export const initialNewRunState: NewRunActionState = {
  status: "idle",
  message: null,
  fields: {},
};

interface BuiltFieldErrors {
  fields: NewRunFieldErrors;
  leftover: ReadonlyArray<{
    field: string;
    messages: readonly string[];
  }>;
}

function readField(formData: FormData, key: string): string {
  const raw = formData.get(key);
  if (typeof raw === "string") {
    return raw.trim();
  }
  return "";
}

/**
 * FastAPI's `_format_loc` (services/api/app/api/errors.py) joins location parts
 * with `.`, stripping the leading source prefix ("body"/"query"/...). So a
 * validation error on `body.tickers[0]` arrives as the field key `tickers.0`,
 * and a bare-field error on `body.trade_date` arrives as `trade_date`. We match
 * `tickers` exactly and `tickers.<index>` via dot-prefix to cover both shapes.
 */
function buildFieldErrors(
  fields: Readonly<Record<string, ReadonlyArray<string>>>,
): BuiltFieldErrors {
  const out: { ticker?: readonly string[]; trade_date?: readonly string[] } =
    {};
  const leftover: Array<{ field: string; messages: readonly string[] }> = [];
  for (const [key, messages] of Object.entries(fields)) {
    if (key === "ticker" || key === "tickers" || key.startsWith("tickers.")) {
      out.ticker = [...messages];
      continue;
    }
    if (key === "trade_date") {
      out.trade_date = [...messages];
      continue;
    }
    leftover.push({ field: key, messages: [...messages] });
  }
  return { fields: out, leftover };
}

function formatLeftoverMessage(
  leftover: ReadonlyArray<{ field: string; messages: readonly string[] }>,
): string {
  const parts = leftover.map(
    (entry) => `${entry.field}: ${entry.messages.join(", ")}`,
  );
  return `Validation failed: ${parts.join("; ")}`;
}

export async function createResearchRun(
  _previousState: NewRunActionState,
  formData: FormData,
): Promise<NewRunActionState> {
  const ticker = readField(formData, "ticker").toUpperCase();
  const tradeDate = readField(formData, "trade_date");

  const fieldErrors: NewRunFieldErrors = {};
  if (ticker.length === 0) {
    fieldErrors.ticker = ["Ticker is required."];
  } else if (ticker.length > TICKER_MAX_LENGTH) {
    fieldErrors.ticker = [
      `Ticker must be ${TICKER_MAX_LENGTH} characters or fewer.`,
    ];
  }
  if (tradeDate.length === 0) {
    fieldErrors.trade_date = ["Trade date is required."];
  } else if (!ISO_DATE_PATTERN.test(tradeDate)) {
    fieldErrors.trade_date = ["Trade date must be YYYY-MM-DD."];
  }
  if (
    fieldErrors.ticker !== undefined ||
    fieldErrors.trade_date !== undefined
  ) {
    return {
      status: "error",
      message: null,
      fields: fieldErrors,
    };
  }

  let createdId: string;
  try {
    const response = await getServerApi().POST("/api/research-runs", {
      body: {
        tickers: [ticker],
        trade_date: tradeDate,
        llm_provider: DEFAULT_PROVIDER,
        llm_model: DEFAULT_MODEL,
        debate_depth: DEFAULT_DEBATE_DEPTH,
      },
    });
    const created = response.data;
    const firstRun = created?.[0];
    if (firstRun === undefined) {
      return {
        status: "error",
        message: "Backend returned no runs.",
        fields: {},
      };
    }
    createdId = firstRun.id;
  } catch (caught) {
    if (isApiError(caught)) {
      const built: BuiltFieldErrors =
        caught.fields !== undefined
          ? buildFieldErrors(caught.fields)
          : { fields: {}, leftover: [] };
      const hasFieldErrors =
        built.fields.ticker !== undefined ||
        built.fields.trade_date !== undefined;
      const leftoverMessage =
        built.leftover.length > 0 ? formatLeftoverMessage(built.leftover) : null;
      const resolvedMessage = hasFieldErrors
        ? leftoverMessage
        : (leftoverMessage ?? caught.detail);
      return {
        status: "error",
        message: resolvedMessage,
        fields: built.fields,
      };
    }
    return {
      status: "error",
      message: "Unable to create run.",
      fields: {},
    };
  }

  updateTag("research-runs");
  redirect(`/research/runs/${createdId}`);
}
