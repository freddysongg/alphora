"use server";

import { updateTag } from "next/cache";

import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import type {
  SubmitOrderActionState,
  SubmitOrderFieldErrors,
} from "./action-state";

type OrderSide = components["schemas"]["OrderSideEnum"];
type OrderType = components["schemas"]["OrderTypeEnum"];

const TICKER_MAX_LENGTH = 16;
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ALLOWED_SIDES: ReadonlySet<OrderSide> = new Set<OrderSide>([
  "buy",
  "sell",
]);
const ALLOWED_ORDER_TYPES: ReadonlySet<OrderType> = new Set<OrderType>([
  "market",
]);

function readField(formData: FormData, key: string): string {
  const raw = formData.get(key);
  if (typeof raw === "string") {
    return raw.trim();
  }
  return "";
}

function isOrderSide(value: string): value is OrderSide {
  return (ALLOWED_SIDES as ReadonlySet<string>).has(value);
}

function isOrderType(value: string): value is OrderType {
  return (ALLOWED_ORDER_TYPES as ReadonlySet<string>).has(value);
}

interface BuiltFieldErrors {
  fields: SubmitOrderFieldErrors;
  leftover: ReadonlyArray<{
    field: string;
    messages: readonly string[];
  }>;
}

function buildFieldErrors(
  fields: Readonly<Record<string, ReadonlyArray<string>>>,
): BuiltFieldErrors {
  const out: SubmitOrderFieldErrors = {};
  const leftover: Array<{ field: string; messages: readonly string[] }> = [];
  for (const [key, messages] of Object.entries(fields)) {
    if (key === "ticker") {
      out.ticker = [...messages];
      continue;
    }
    if (key === "quantity") {
      out.quantity = [...messages];
      continue;
    }
    if (key === "side") {
      out.side = [...messages];
      continue;
    }
    if (key === "order_type") {
      out.order_type = [...messages];
      continue;
    }
    if (key === "portfolio_id") {
      out.portfolio_id = [...messages];
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

export async function submitPaperOrder(
  _previousState: SubmitOrderActionState,
  formData: FormData,
): Promise<SubmitOrderActionState> {
  const portfolioId = readField(formData, "portfolio_id");
  const ticker = readField(formData, "ticker").toUpperCase();
  const sideRaw = readField(formData, "side");
  const orderTypeRaw = readField(formData, "order_type");
  const quantityRaw = readField(formData, "quantity");

  const fieldErrors: SubmitOrderFieldErrors = {};
  if (portfolioId.length === 0 || !UUID_PATTERN.test(portfolioId)) {
    fieldErrors.portfolio_id = ["Portfolio is required."];
  }
  if (ticker.length === 0) {
    fieldErrors.ticker = ["Ticker is required."];
  } else if (ticker.length > TICKER_MAX_LENGTH) {
    fieldErrors.ticker = [
      `Ticker must be ${TICKER_MAX_LENGTH} characters or fewer.`,
    ];
  }
  if (!isOrderSide(sideRaw)) {
    fieldErrors.side = ["Invalid side."];
  } else if (sideRaw === "sell") {
    fieldErrors.side = ["Sell orders are disabled (long-only)."];
  }
  if (!isOrderType(orderTypeRaw)) {
    fieldErrors.order_type = ["Invalid order type."];
  }
  const quantity = Number.parseInt(quantityRaw, 10);
  if (!Number.isFinite(quantity) || quantity <= 0) {
    fieldErrors.quantity = ["Quantity must be a positive integer."];
  }
  if (Object.keys(fieldErrors).length > 0) {
    return {
      status: "error",
      message: null,
      fields: fieldErrors,
    };
  }

  try {
    await getServerApi().POST("/api/paper/orders", {
      body: {
        portfolio_id: portfolioId,
        ticker,
        side: sideRaw as OrderSide,
        quantity,
        order_type: orderTypeRaw as OrderType,
        source_run_id: null,
      },
    });
  } catch (caught) {
    if (isApiError(caught)) {
      const built: BuiltFieldErrors =
        caught.fields !== undefined
          ? buildFieldErrors(caught.fields)
          : { fields: {}, leftover: [] };
      const hasFieldErrors = Object.keys(built.fields).length > 0;
      const leftoverMessage =
        built.leftover.length > 0
          ? formatLeftoverMessage(built.leftover)
          : null;
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
      message: "Unable to submit order.",
      fields: {},
    };
  }

  updateTag("paper-portfolio");
  updateTag("paper-orders");
  return {
    status: "ok",
    message: null,
    fields: {},
  };
}
