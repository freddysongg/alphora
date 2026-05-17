const FALLBACK = "—";
const CENTS_PER_DOLLAR = 100;

export function centsToDollars(cents: number | null): string {
  if (cents === null) {
    return FALLBACK;
  }
  if (!Number.isFinite(cents)) {
    return FALLBACK;
  }
  const dollars = cents / CENTS_PER_DOLLAR;
  return dollars.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
