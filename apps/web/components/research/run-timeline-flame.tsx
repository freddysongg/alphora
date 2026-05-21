"use client";

import type { ReactElement } from "react";
import { useMemo, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui";
import type { components } from "@/lib/api";

type LlmCallLog = components["schemas"]["LlmCallLogPublic"];

export interface RunTimelineFlameProps {
  calls: readonly LlmCallLog[];
}

interface FlameBar {
  id: string;
  stage: string;
  agentName: string | null;
  model: string;
  startMs: number;
  durationMs: number;
  costUsd: number;
  inputTokens: number;
  outputTokens: number;
  status: LlmCallLog["status"];
  budgetAction: LlmCallLog["budget_action"];
}

const STAGE_COLORS: Record<string, string> = {
  macro_synthesis: "bg-accent",
  sector_synthesis: "bg-accent/80",
  company_synthesis: "bg-accent/60",
  portfolio_synthesis: "bg-accent/40",
  judge: "bg-warning",
  extraction: "bg-success",
  hypothesis_dedup: "bg-fg-muted",
  unknown: "bg-fg-subtle",
};

const STATUS_BORDER: Record<LlmCallLog["status"], string> = {
  success: "border-line",
  error: "border-danger",
  budget_paused: "border-warning",
  budget_killed: "border-danger",
};

const FALLBACK_STAGE_COLOR = "bg-fg-subtle";

function resolveStageColor(stage: string | null): string {
  if (stage === null) {
    return STAGE_COLORS.unknown ?? FALLBACK_STAGE_COLOR;
  }
  return STAGE_COLORS[stage] ?? "bg-fg-muted";
}

interface RowWithStart {
  row: LlmCallLog;
  startedMs: number;
}

function buildFlameBars(rows: readonly LlmCallLog[]): FlameBar[] {
  if (rows.length === 0) {
    return [];
  }
  const withStart: RowWithStart[] = rows.map((row) => {
    const persistedMs = Date.parse(row.created_at);
    const startedMs = Number.isFinite(persistedMs)
      ? persistedMs - row.latency_ms
      : 0;
    return { row, startedMs };
  });
  const sorted = [...withStart].sort((a, b) => a.startedMs - b.startedMs);
  const head = sorted[0];
  if (head === undefined) {
    return [];
  }
  const firstStart = head.startedMs;
  return sorted.map(({ row, startedMs }) => {
    const startMs = startedMs - firstStart;
    return {
      id: row.id,
      stage: row.stage ?? "unknown",
      agentName: row.agent_name,
      model: row.model,
      startMs,
      durationMs: Math.max(row.latency_ms, 1),
      costUsd: Number(row.cost_usd),
      inputTokens: row.input_tokens,
      outputTokens: row.output_tokens,
      status: row.status,
      budgetAction: row.budget_action,
    };
  });
}

function formatMs(value: number): string {
  if (value < 1_000) {
    return `${Math.round(value)}ms`;
  }
  if (value < 60_000) {
    return `${(value / 1_000).toFixed(1)}s`;
  }
  return `${(value / 60_000).toFixed(1)}m`;
}

function formatUsd(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  return `$${value.toFixed(4)}`;
}

export function RunTimelineFlame(props: RunTimelineFlameProps): ReactElement {
  const { calls } = props;
  const bars = useMemo(() => buildFlameBars(calls), [calls]);
  const totalMs = useMemo(() => {
    if (bars.length === 0) {
      return 0;
    }
    return Math.max(...bars.map((bar) => bar.startMs + bar.durationMs));
  }, [bars]);

  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (bars.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>RUN TIMELINE</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-fg-subtle">
            No LLM calls recorded for this run yet.
          </p>
        </CardContent>
      </Card>
    );
  }

  const selectedBar = bars.find((bar) => bar.id === selectedId) ?? null;
  const stages = Array.from(new Set(bars.map((b) => b.stage))).sort();
  const stageToRow: Map<string, number> = new Map(
    stages.map((stage, index) => [stage, index]),
  );
  const rowHeight = 22;
  const rowGap = 4;
  const trackHeight = stages.length * (rowHeight + rowGap);

  return (
    <Card>
      <CardHeader>
        <CardTitle>RUN TIMELINE</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
            <span>{bars.length} CALLS · {formatMs(totalMs)} TOTAL</span>
            <span>HOVER FOR DETAIL</span>
          </div>
          <div className="flex">
            <ul className="w-44 shrink-0 flex flex-col" style={{ gap: rowGap }}>
              {stages.map((stage) => (
                <li
                  key={stage}
                  className="flex items-center text-[11px] tracking-[0.14em] uppercase text-fg-muted font-mono"
                  style={{ height: rowHeight }}
                >
                  {stage}
                </li>
              ))}
            </ul>
            <div
              className="relative flex-1 border-l border-line/40"
              style={{ height: trackHeight }}
              data-testid="run-timeline-track"
            >
              {bars.map((bar) => {
                const leftPct = totalMs === 0 ? 0 : (bar.startMs / totalMs) * 100;
                const widthPct =
                  totalMs === 0 ? 100 : Math.max((bar.durationMs / totalMs) * 100, 0.5);
                const rowIndex = stageToRow.get(bar.stage) ?? 0;
                const top = rowIndex * (rowHeight + rowGap);
                const isSelected = selectedId === bar.id;
                const colorClass = resolveStageColor(bar.stage);
                const borderClass = STATUS_BORDER[bar.status];
                return (
                  <button
                    key={bar.id}
                    type="button"
                    aria-label={`${bar.stage} ${bar.agentName ?? ""} ${formatMs(bar.durationMs)}`}
                    onMouseEnter={() => setSelectedId(bar.id)}
                    onFocus={() => setSelectedId(bar.id)}
                    onClick={() => setSelectedId(bar.id)}
                    className={`absolute border ${colorClass} ${borderClass} ${
                      isSelected ? "ring-1 ring-accent" : ""
                    } transition-opacity hover:opacity-80 cursor-pointer`}
                    style={{
                      left: `${leftPct}%`,
                      width: `${widthPct}%`,
                      top,
                      height: rowHeight,
                    }}
                    data-testid="run-timeline-bar"
                    data-stage={bar.stage}
                  />
                );
              })}
            </div>
          </div>
          {selectedBar !== null ? (
            <div
              className="grid grid-cols-2 md:grid-cols-4 gap-4 border-t border-line pt-4"
              data-testid="run-timeline-selected"
            >
              <DetailCell label="STAGE / AGENT" value={`${selectedBar.stage} · ${selectedBar.agentName ?? "—"}`} />
              <DetailCell label="MODEL" value={selectedBar.model} mono />
              <DetailCell label="LATENCY" value={formatMs(selectedBar.durationMs)} />
              <DetailCell label="COST" value={formatUsd(selectedBar.costUsd)} />
              <DetailCell label="INPUT TOKENS" value={selectedBar.inputTokens.toLocaleString()} />
              <DetailCell label="OUTPUT TOKENS" value={selectedBar.outputTokens.toLocaleString()} />
              <DetailCell label="STATUS" value={selectedBar.status.toUpperCase()} />
              <DetailCell
                label="BUDGET ACTION"
                value={selectedBar.budgetAction?.toUpperCase() ?? "—"}
              />
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

interface DetailCellProps {
  label: string;
  value: string;
  mono?: boolean;
}

function DetailCell(props: DetailCellProps): ReactElement {
  const { label, value, mono } = props;
  const valueClass = mono
    ? "text-sm font-mono tabular-nums text-fg"
    : "text-sm text-fg tabular-nums";
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
        {label}
      </span>
      <span className={valueClass}>{value}</span>
    </div>
  );
}
