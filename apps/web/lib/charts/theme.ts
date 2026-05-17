import { chartAlphas, colorTokens } from "@/lib/tokens";

export const chartTheme = {
  axis: { stroke: colorTokens.line, tickFill: colorTokens.fgMuted },
  grid: { stroke: chartAlphas.gridDot },
  series: { stroke: colorTokens.accent, width: 1.5 },
  areaFillStops: [
    { offset: "0%", color: chartAlphas.areaFillTop },
    { offset: "100%", color: chartAlphas.areaFillBottom },
  ],
  tooltip: { background: colorTokens.surface, border: colorTokens.line },
} as const;
