"use client";

import { useCallback, useRef, useState } from "react";
import type { ReactElement } from "react";
import Link from "next/link";
import type { Route } from "next";

import { useRunSseEvent } from "@/components/research/run-sse-context";
import type { components } from "@/lib/api";

type RunCostEstimate = components["schemas"]["RunCostEstimate"];

const SSE_EVENT_LOG = "log";
const COST_EVENT_NAME = "cost";

export type BudgetAction = "allow" | "warn" | "pause" | "kill";

export interface CostMeterState {
  cumulativeCostUsd: number;
  inputTokensTotal: number;
  cachedInputTokensTotal: number;
  lastModel: string | null;
  lastBudgetAction: BudgetAction | null;
}

export interface LiveCostStripProps {
  runId: string;
  initialState: CostMeterState;
  initialSeenLogIds: readonly string[];
  costEstimate: RunCostEstimate | null;
}

interface RawCostEvent {
  event?: unknown;
  log_id?: unknown;
  model?: unknown;
  input_tokens?: unknown;
  cached_input_tokens?: unknown;
  cost_usd?: unknown;
  cumulative_run_cost_usd?: unknown;
  budget_action?: unknown;
}

interface RawLogEvent {
  data?: unknown;
}

const KNOWN_ACTIONS: readonly BudgetAction[] = ["allow", "warn", "pause", "kill"];

function isBudgetAction(value: unknown): value is BudgetAction {
  return (
    typeof value === "string"
    && (KNOWN_ACTIONS as readonly string[]).includes(value)
  );
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function reduceCostEvent(
  prev: CostMeterState,
  cost: RawCostEvent,
): CostMeterState {
  const cumulative = toNumber(cost.cumulative_run_cost_usd);
  const callCost = toNumber(cost.cost_usd);
  const inputTokens = toNumber(cost.input_tokens) ?? 0;
  const cachedInputTokens = toNumber(cost.cached_input_tokens) ?? 0;
  const model = typeof cost.model === "string" ? cost.model : prev.lastModel;
  const action = isBudgetAction(cost.budget_action)
    ? cost.budget_action
    : prev.lastBudgetAction;
  const nextCumulative = cumulative
    ?? prev.cumulativeCostUsd + (callCost ?? 0);
  return {
    cumulativeCostUsd: nextCumulative,
    inputTokensTotal: prev.inputTokensTotal + inputTokens,
    cachedInputTokensTotal: prev.cachedInputTokensTotal + cachedInputTokens,
    lastModel: model,
    lastBudgetAction: action,
  };
}

function parseCostEventFromLog(raw: string): RawCostEvent | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (
    typeof parsed !== "object"
    || parsed === null
    || Array.isArray(parsed)
  ) {
    return null;
  }
  const logEvent = parsed as RawLogEvent;
  const data = logEvent.data;
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    return null;
  }
  const cost = data as RawCostEvent;
  if (cost.event !== COST_EVENT_NAME) {
    return null;
  }
  return cost;
}

function formatUsd(value: number): string {
  return `$${value.toFixed(4)}`;
}

function parseEstimate(raw: string | undefined): number | null {
  if (raw === undefined) {
    return null;
  }
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

export function LiveCostStrip(props: LiveCostStripProps): ReactElement {
  const { runId, initialState, initialSeenLogIds, costEstimate } = props;
  const [state, setState] = useState<CostMeterState>(initialState);
  const seenLogIdsRef = useRef<Set<string>>(new Set(initialSeenLogIds));

  const onLog = useCallback((raw: string): void => {
    const cost = parseCostEventFromLog(raw);
    if (cost === null) {
      return;
    }
    const logId = typeof cost.log_id === "string" ? cost.log_id : null;
    if (logId !== null) {
      if (seenLogIdsRef.current.has(logId)) {
        return;
      }
      seenLogIdsRef.current.add(logId);
    }
    setState((prev) => reduceCostEvent(prev, cost));
  }, []);

  useRunSseEvent(SSE_EVENT_LOG, onLog);

  const estimateValue = parseEstimate(costEstimate?.estimated_total_usd);
  const observabilityHref = `/research/runs/${runId}/observability` as Route;

  return (
    <div className="flex items-center gap-6 border-t border-line pt-4 text-xs">
      <span className="text-fg-muted">
        Cost{" "}
        <span className="font-mono tabular-nums text-fg">
          {formatUsd(state.cumulativeCostUsd)}
        </span>
      </span>
      {estimateValue !== null ? (
        <span className="text-fg-subtle">
          Estimate{" "}
          <span className="font-mono tabular-nums text-fg-muted">
            {formatUsd(estimateValue)}
          </span>
        </span>
      ) : null}
      <span className="text-fg-subtle">
        Model{" "}
        <span className="font-mono text-fg-muted">
          {state.lastModel ?? "—"}
        </span>
      </span>
      <div className="flex-1" />
      <Link
        href={observabilityHref}
        className="text-fg-muted hover:text-fg underline-offset-2 hover:underline"
      >
        View observability →
      </Link>
    </div>
  );
}
