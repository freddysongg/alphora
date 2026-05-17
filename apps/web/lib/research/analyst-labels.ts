import type { components } from "@/lib/api";

type AnalystKind = components["schemas"]["AnalystKindEnum"];

export const ANALYST_ORDER: readonly AnalystKind[] = [
  "bull",
  "bear",
  "macro",
  "fundamentals",
  "sentiment",
  "risk",
];

export const ANALYST_LABELS: Record<AnalystKind, string> = {
  bull: "Bull Case",
  bear: "Bear Case",
  macro: "Macro",
  fundamentals: "Fundamentals",
  sentiment: "Sentiment",
  risk: "Risk",
};

const ANALYST_ORDER_INDEX: ReadonlyMap<AnalystKind, number> = new Map(
  ANALYST_ORDER.map((kind, index) => [kind, index]),
);

export function isAnalystKind(value: string): value is AnalystKind {
  return ANALYST_ORDER_INDEX.has(value as AnalystKind);
}

export function resolveAnalystLabel(value: string): string {
  if (isAnalystKind(value)) {
    return ANALYST_LABELS[value];
  }
  return value;
}

export function compareAnalysts(left: string, right: string): number {
  const leftIndex = isAnalystKind(left)
    ? (ANALYST_ORDER_INDEX.get(left) ?? Number.MAX_SAFE_INTEGER)
    : Number.MAX_SAFE_INTEGER;
  const rightIndex = isAnalystKind(right)
    ? (ANALYST_ORDER_INDEX.get(right) ?? Number.MAX_SAFE_INTEGER)
    : Number.MAX_SAFE_INTEGER;
  if (leftIndex !== rightIndex) {
    return leftIndex - rightIndex;
  }
  return left.localeCompare(right);
}
