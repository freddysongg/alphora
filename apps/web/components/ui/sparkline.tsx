"use client";

import { useId } from "react";
import type { ReactElement } from "react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { chartTheme } from "@/lib/charts/theme";

export interface SparklineProps {
  data: number[];
  width?: number | "100%";
  height?: number;
  isAnimationActive?: boolean;
}

interface SparklineDatum {
  index: number;
  value: number;
}

function toChartData(data: number[]): SparklineDatum[] {
  return data.map((value, index) => ({ index, value }));
}

export function Sparkline(props: SparklineProps): ReactElement {
  const {
    data,
    width = 120,
    height = 32,
    isAnimationActive = false,
  } = props;
  const gradientId = useId();
  const chartData = toChartData(data);
  const [topStop, bottomStop] = chartTheme.areaFillStops;

  return (
    <div style={{ width, height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={chartData}
          margin={{ top: 2, right: 0, bottom: 2, left: 0 }}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset={topStop?.offset ?? "0%"} stopColor={topStop?.color ?? "rgba(185,140,255,0.22)"} />
              <stop offset={bottomStop?.offset ?? "100%"} stopColor={bottomStop?.color ?? "rgba(185,140,255,0)"} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="value"
            stroke={chartTheme.series.stroke}
            strokeWidth={chartTheme.series.width}
            fill={`url(#${gradientId})`}
            isAnimationActive={isAnimationActive}
            dot={false}
            activeDot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
