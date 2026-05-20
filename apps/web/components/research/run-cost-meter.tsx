"use client";

import { useCallback, useRef, useState } from "react";
import type { ReactElement } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui";
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

export interface RunCostMeterProps {
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
  return typeof value === "string"
    && (KNOWN_ACTIONS as readonly string[]).includes(value);
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

function formatRatio(num: number, denom: number): string {
  if (denom <= 0) {
    return "—";
  }
  const ratio = num / denom;
  return `${(ratio * 100).toFixed(1)}%`;
}

const actionLabel: Record<BudgetAction, string> = {
  allow: "ALLOW",
  warn: "WARN",
  pause: "PAUSE",
  kill: "KILL",
};

const actionToneClass: Record<BudgetAction, string> = {
  allow: "text-fg",
  warn: "text-warning",
  pause: "text-warning",
  kill: "text-danger",
};

export function RunCostMeter(props: RunCostMeterProps): ReactElement {
  const { initialState, initialSeenLogIds, costEstimate } = props;
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

  const action = state.lastBudgetAction;
  const actionDisplay = action !== null ? actionLabel[action] : "—";
  const actionTone = action !== null ? actionToneClass[action] : "text-fg-subtle";
  const estimateValue = parseEstimate(costEstimate?.estimated_total_usd);
  const estimateP95Value = parseEstimate(costEstimate?.estimated_p95_usd);
  const estimateDisplay = estimateValue !== null
    ? formatUsd(estimateValue)
    : "—";
  const estimateDeltaTone = resolveEstimateTone(
    state.cumulativeCostUsd,
    estimateP95Value,
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>RUN COST</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
          <MeterCell
            label="CUMULATIVE COST"
            value={formatUsd(state.cumulativeCostUsd)}
            valueClassName={estimateDeltaTone}
          />
          <MeterCell
            label="PRE-FLIGHT ESTIMATE"
            value={estimateDisplay}
          />
          <MeterCell
            label="CACHE HIT RATE"
            value={formatRatio(
              state.cachedInputTokensTotal,
              state.inputTokensTotal,
            )}
          />
          <MeterCell
            label="MODEL"
            value={state.lastModel ?? "—"}
            mono
          />
          <MeterCell
            label="BUDGET ACTION"
            value={actionDisplay}
            valueClassName={actionTone}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function parseEstimate(raw: string | undefined): number | null {
  if (raw === undefined) {
    return null;
  }
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function resolveEstimateTone(
  actualUsd: number,
  estimateP95Usd: number | null,
): string {
  if (estimateP95Usd === null || estimateP95Usd <= 0) {
    return "text-fg";
  }
  if (actualUsd > estimateP95Usd) {
    return "text-danger";
  }
  return "text-fg";
}

interface MeterCellProps {
  label: string;
  value: string;
  mono?: boolean;
  valueClassName?: string;
}

function MeterCell(props: MeterCellProps): ReactElement {
  const { label, value, mono, valueClassName } = props;
  const valueClass = mono
    ? `text-base font-mono tabular-nums ${valueClassName ?? "text-fg"}`
    : `text-base ${valueClassName ?? "text-fg"} tabular-nums`;
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
        {label}
      </span>
      <span className={valueClass}>{value}</span>
    </div>
  );
}
