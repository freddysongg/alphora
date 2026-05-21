interface TickerSource {
  readonly ticker: string | null;
}

export function dedupeTickers(runs: readonly TickerSource[]): string[] {
  const unique = new Set<string>();
  for (const run of runs) {
    if (run.ticker !== null) {
      unique.add(run.ticker);
    }
  }
  return Array.from(unique).sort((left, right) => left.localeCompare(right));
}
