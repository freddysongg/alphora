export const FACTOR_KEYS = [
  "quality",
  "valuation",
  "momentum",
  "volatility",
  "sentiment",
] as const;

export type FactorKey = (typeof FACTOR_KEYS)[number];

export type FactorWeights = Record<FactorKey, number>;

export const WEIGHT_FIELD_PREFIX = "weight_";

function isFactorKey(value: string): value is FactorKey {
  return (FACTOR_KEYS as readonly string[]).includes(value);
}

function clampWeight(value: number): number {
  if (value < 0) {
    return 0;
  }
  if (value > 1) {
    return 1;
  }
  return value;
}

export function makeDefaultWeights(): FactorWeights {
  return {
    quality: 0,
    valuation: 0,
    momentum: 0,
    volatility: 0,
    sentiment: 0,
  };
}

export function formDataToWeights(formData: FormData): FactorWeights {
  const weights = makeDefaultWeights();
  for (const key of FACTOR_KEYS) {
    const raw = formData.get(`${WEIGHT_FIELD_PREFIX}${key}`);
    if (typeof raw !== "string") {
      continue;
    }
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) {
      continue;
    }
    weights[key] = clampWeight(parsed);
  }
  return weights;
}

export function recordToWeights(
  record: Readonly<Record<string, number>>,
): FactorWeights {
  const weights = makeDefaultWeights();
  for (const [key, value] of Object.entries(record)) {
    if (!isFactorKey(key)) {
      continue;
    }
    if (!Number.isFinite(value)) {
      continue;
    }
    weights[key] = clampWeight(value);
  }
  return weights;
}
