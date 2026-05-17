export const colorTokens = {
  canvas: "#06050A",
  panel: "#11101A",
  surface: "#1A1728",
  surface2: "#211C33",

  line: "#332D48",
  lineStrong: "#4A2E8A",

  accent: "#B98CFF",
  accentSoft: "#D9C2FF",
  accentDeep: "#7A4DFF",
  accentPress: "#4A2E8A",
  accentText: "#D8B4FE",

  warn: "#E879F9",
  danger: "#FF6B7A",
  success: "#B98CFF",

  fg: "#ECE6FA",
  fgMuted: "#9A92B5",
  fgSubtle: "#5E5878",
} as const;

export const chartAlphas = {
  areaFillTop: "rgba(185, 140, 255, 0.22)",
  areaFillBottom: "rgba(185, 140, 255, 0)",
  gridDot: "rgba(217, 194, 255, 0.06)",
  liveHalo: "rgba(185, 140, 255, 0.18)",
} as const;

export type ColorToken = keyof typeof colorTokens;
