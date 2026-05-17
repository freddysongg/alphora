"use client";

import { useId } from "react";
import type { ReactElement } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { chartTheme } from "@/lib/charts/theme";
import { colorTokens } from "@/lib/tokens";
import { sampleFactorHistory } from "@/lib/fixtures/tickers";

const seriesConfig = [
  { dataKey: "quality" as const, stroke: colorTokens.accent },
  { dataKey: "valuation" as const, stroke: colorTokens.accentSoft },
  { dataKey: "momentum" as const, stroke: colorTokens.accentText },
];

interface ChartDatum {
  date: string;
  quality: number;
  valuation: number;
  momentum: number;
}

const tooltipStyle = {
  background: chartTheme.tooltip.background,
  border: `1px solid ${chartTheme.tooltip.border}`,
  borderRadius: "6px",
  padding: "8px 10px",
  fontFamily: "var(--font-mono)",
  fontSize: "12px",
  color: colorTokens.fg,
} as const;

export function FactorHistoryChart(): ReactElement {
  const gradientIdQuality = useId();
  const gradientIdValuation = useId();
  const gradientIdMomentum = useId();
  const gradientIds: Record<string, string> = {
    quality: gradientIdQuality,
    valuation: gradientIdValuation,
    momentum: gradientIdMomentum,
  };
  const data: ChartDatum[] = [...sampleFactorHistory];

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 8, right: 8, bottom: 0, left: -16 }}
        >
          <defs>
            {seriesConfig.map((series) => (
              <linearGradient
                key={series.dataKey}
                id={gradientIds[series.dataKey]}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop offset="0%" stopColor={series.stroke} stopOpacity={0.22} />
                <stop offset="100%" stopColor={series.stroke} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid stroke={chartTheme.grid.stroke} vertical={false} />
          <XAxis
            dataKey="date"
            stroke={chartTheme.axis.stroke}
            tick={{ fill: chartTheme.axis.tickFill, fontSize: 11, fontFamily: "var(--font-mono)" }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            stroke={chartTheme.axis.stroke}
            tick={{ fill: chartTheme.axis.tickFill, fontSize: 11, fontFamily: "var(--font-mono)" }}
            tickLine={false}
            axisLine={false}
            domain={[0, 1]}
            width={32}
          />
          <Tooltip contentStyle={tooltipStyle} cursor={{ stroke: chartTheme.axis.stroke }} />
          {seriesConfig.map((series) => (
            <Area
              key={series.dataKey}
              type="monotone"
              dataKey={series.dataKey}
              stroke={series.stroke}
              strokeWidth={1.5}
              fill={`url(#${gradientIds[series.dataKey]})`}
              isAnimationActive={false}
              dot={false}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
