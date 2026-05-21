"use client";

import type { ReactElement } from "react";
import { useMemo } from "react";
import {
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui";
import type { components } from "@/lib/api";
import { chartTheme } from "@/lib/charts/theme";
import { colorTokens } from "@/lib/tokens";

type LeakageRun = components["schemas"]["LeakageRunPublic"];

export interface LeakageChartProps {
  runs: readonly LeakageRun[];
}

interface ChartDatum {
  index: number;
  label: string;
  meanDecay: number;
  maxDecay: number;
  threshold: number;
  flagged: boolean;
  caseCount: number;
  createdAt: string;
}

function toChartData(runs: readonly LeakageRun[]): ChartDatum[] {
  const ordered = [...runs].sort((a, b) =>
    a.created_at.localeCompare(b.created_at),
  );
  return ordered.map((row, index) => ({
    index,
    label: row.created_at.slice(5, 10),
    meanDecay: row.mean_decay,
    maxDecay: row.max_decay,
    threshold: row.threshold,
    flagged: row.flagged,
    caseCount: row.case_count,
    createdAt: row.created_at,
  }));
}

function formatPercent(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

export function LeakageChart(props: LeakageChartProps): ReactElement {
  const { runs } = props;
  const data = useMemo(() => toChartData(runs), [runs]);
  if (data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>LEAKAGE DECAY</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-fg-subtle">
            No leakage holdout runs recorded yet.
          </p>
        </CardContent>
      </Card>
    );
  }
  const threshold = data[0]?.threshold ?? 0;
  const flaggedCount = data.filter((d) => d.flagged).length;
  return (
    <Card>
      <CardHeader>
        <CardTitle>LEAKAGE DECAY</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted mb-4">
          <span data-testid="leakage-chart-summary">
            {data.length} RUNS · {flaggedCount} FLAGGED · THRESHOLD{" "}
            {formatPercent(threshold)}
          </span>
        </div>
        <div className="h-64" data-testid="leakage-chart-canvas">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 16, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid.stroke} />
              <XAxis
                dataKey="label"
                tick={{ fill: chartTheme.axis.tickFill, fontSize: 10 }}
                stroke={chartTheme.axis.stroke}
              />
              <YAxis
                tick={{ fill: chartTheme.axis.tickFill, fontSize: 10 }}
                stroke={chartTheme.axis.stroke}
                tickFormatter={(value: number) => `${(value * 100).toFixed(0)}%`}
                domain={[0, 1]}
              />
              <ReferenceLine
                y={threshold}
                stroke={colorTokens.warn}
                strokeDasharray="3 3"
                label={{
                  value: "threshold",
                  fill: colorTokens.fgMuted,
                  fontSize: 10,
                  position: "right",
                }}
              />
              <Tooltip
                contentStyle={{
                  background: chartTheme.tooltip.background,
                  border: `1px solid ${chartTheme.tooltip.border}`,
                  fontSize: 11,
                }}
                formatter={(value: number) => formatPercent(value)}
                labelStyle={{ color: chartTheme.axis.tickFill }}
              />
              <Line
                type="monotone"
                dataKey="meanDecay"
                name="mean decay"
                stroke={chartTheme.series.stroke}
                strokeWidth={chartTheme.series.width}
                dot={false}
                isAnimationActive={false}
              />
              <Scatter dataKey="maxDecay" name="max decay" isAnimationActive={false}>
                {data.map((entry) => (
                  <Cell
                    key={entry.createdAt}
                    fill={entry.flagged ? colorTokens.danger : colorTokens.accentSoft}
                  />
                ))}
              </Scatter>
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-6 border-t border-line pt-4">
          <table className="w-full text-sm" data-testid="leakage-chart-table">
            <thead>
              <tr className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
                <th className="text-left py-2">DATE</th>
                <th className="text-right py-2">CASES</th>
                <th className="text-right py-2">MEAN</th>
                <th className="text-right py-2">MAX</th>
                <th className="text-right py-2">STATUS</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr
                  key={row.createdAt}
                  className="border-t border-line/40 font-mono tabular-nums text-fg"
                  data-testid="leakage-chart-row"
                >
                  <td className="py-2">{row.createdAt.slice(0, 10)}</td>
                  <td className="text-right py-2">{row.caseCount}</td>
                  <td className="text-right py-2">{formatPercent(row.meanDecay)}</td>
                  <td className="text-right py-2">{formatPercent(row.maxDecay)}</td>
                  <td
                    className={`text-right py-2 ${row.flagged ? "text-danger" : "text-fg-muted"}`}
                  >
                    {row.flagged ? "flagged" : "ok"}
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
