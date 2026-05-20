"use client";

import type { ReactElement } from "react";
import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui";
import type { components } from "@/lib/api";
import { chartTheme } from "@/lib/charts/theme";
import { colorTokens } from "@/lib/tokens";

type RunCostLedger = components["schemas"]["RunCostLedger"];
type StageCostRow = components["schemas"]["StageCostRow"];

export interface CostLedgerProps {
  ledger: RunCostLedger | null;
}

const STAGE_COLOR_TOKENS: Record<string, string> = {
  macro_synthesis: colorTokens.accent,
  sector_synthesis: colorTokens.accentSoft,
  company_synthesis: colorTokens.accentDeep,
  portfolio_synthesis: colorTokens.accentPress,
  judge: colorTokens.warn,
  extraction: colorTokens.success,
  hypothesis_dedup: colorTokens.fgMuted,
  unknown: colorTokens.fgSubtle,
};

function resolveStageColor(stage: string): string {
  return STAGE_COLOR_TOKENS[stage] ?? colorTokens.fgMuted;
}

function formatUsd(value: string | number): string {
  const parsed = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(parsed)) {
    return "—";
  }
  return `$${parsed.toFixed(4)}`;
}

function formatRatio(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

interface ChartDatum {
  stage: string;
  cost: number;
  fill: string;
}

function toChartData(stages: readonly StageCostRow[]): ChartDatum[] {
  return stages.map((row) => ({
    stage: row.stage,
    cost: Number(row.total_cost_usd),
    fill: resolveStageColor(row.stage),
  }));
}

export function CostLedger(props: CostLedgerProps): ReactElement {
  const { ledger } = props;
  const chartData = useMemo(
    () => toChartData(ledger?.stages ?? []),
    [ledger?.stages],
  );

  if (ledger === null || ledger.stages.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>COST LEDGER</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-fg-subtle">
            No LLM cost recorded for this run yet.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>COST LEDGER</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          <div className="lg:col-span-2">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3" data-testid="cost-ledger-totals">
              <SummaryRow label="TOTAL COST" value={formatUsd(ledger.total_cost_usd)} />
              <SummaryRow label="TOTAL CALLS" value={ledger.total_calls.toLocaleString()} />
              <SummaryRow
                label="INPUT TOKENS"
                value={ledger.total_input_tokens.toLocaleString()}
              />
              <SummaryRow
                label="OUTPUT TOKENS"
                value={ledger.total_output_tokens.toLocaleString()}
              />
              <SummaryRow
                label="CACHE HIT RATE"
                value={formatRatio(ledger.cache_hit_rate)}
              />
              <SummaryRow
                label="CACHED TOKENS"
                value={ledger.total_cached_input_tokens.toLocaleString()}
              />
            </dl>
          </div>
          <div className="lg:col-span-3 h-48" data-testid="cost-ledger-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid.stroke} />
                <XAxis
                  dataKey="stage"
                  tick={{ fill: chartTheme.axis.tickFill, fontSize: 10 }}
                  stroke={chartTheme.axis.stroke}
                  interval={0}
                  angle={-12}
                  textAnchor="end"
                  height={50}
                />
                <YAxis
                  tick={{ fill: chartTheme.axis.tickFill, fontSize: 10 }}
                  stroke={chartTheme.axis.stroke}
                  tickFormatter={(value: number) => `$${value.toFixed(2)}`}
                />
                <Tooltip
                  cursor={{ fill: chartTheme.grid.stroke }}
                  contentStyle={{
                    background: chartTheme.tooltip.background,
                    border: `1px solid ${chartTheme.tooltip.border}`,
                    fontSize: 11,
                  }}
                  formatter={(value: number) => formatUsd(value)}
                  labelStyle={{ color: chartTheme.axis.tickFill }}
                />
                <Bar dataKey="cost" radius={[2, 2, 0, 0]} isAnimationActive={false}>
                  {chartData.map((entry) => (
                    <Cell key={entry.stage} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="mt-6 border-t border-line pt-4">
          <table className="w-full text-sm" data-testid="cost-ledger-table">
            <thead>
              <tr className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
                <th className="text-left py-2">STAGE</th>
                <th className="text-right py-2">CALLS</th>
                <th className="text-right py-2">COST</th>
                <th className="text-right py-2">INPUT TOK</th>
                <th className="text-right py-2">CACHED TOK</th>
                <th className="text-right py-2">CACHE %</th>
                <th className="text-left py-2 pl-4">MODELS</th>
              </tr>
            </thead>
            <tbody>
              {ledger.stages.map((row) => (
                <tr
                  key={row.stage}
                  className="border-t border-line/40 font-mono tabular-nums text-fg"
                >
                  <td className="py-2">
                    <span
                      className="inline-block w-2 h-2 mr-2"
                      style={{ background: resolveStageColor(row.stage) }}
                    />
                    {row.stage}
                  </td>
                  <td className="text-right py-2">{row.call_count}</td>
                  <td className="text-right py-2">{formatUsd(row.total_cost_usd)}</td>
                  <td className="text-right py-2">{row.total_input_tokens.toLocaleString()}</td>
                  <td className="text-right py-2">{row.total_cached_input_tokens.toLocaleString()}</td>
                  <td className="text-right py-2">{formatRatio(row.cache_hit_rate)}</td>
                  <td className="text-left py-2 pl-4 text-fg-muted">
                    {row.models.join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

interface SummaryRowProps {
  label: string;
  value: string;
}

function SummaryRow(props: SummaryRowProps): ReactElement {
  const { label, value } = props;
  return (
    <>
      <dt className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
        {label}
      </dt>
      <dd className="text-base text-fg font-mono tabular-nums text-right">
        {value}
      </dd>
    </>
  );
}
