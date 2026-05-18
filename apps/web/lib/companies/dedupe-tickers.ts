interface TickerSource {
  readonly ticker: string;
}

export function dedupeTickers(runs: readonly TickerSource[]): string[] {
  const unique = new Set<string>();
  for (const run of runs) {
    unique.add(run.ticker);
  }
  return Array.from(unique).sort((left, right) => left.localeCompare(right));
}
