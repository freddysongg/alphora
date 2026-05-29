import type { components } from "@/lib/api";
import type { ApiKeyStatus, DataSourceEntry } from "@/lib/data-health/types";

type ProviderMatrix = components["schemas"]["ProviderMatrix"];
type ProviderMatrixCell = components["schemas"]["ProviderMatrixCell"];
type ProviderCheckStatus = components["schemas"]["ProviderCheckStatusEnum"];

export interface ProviderOverviewRow {
  readonly provider: string;
  readonly sourceCount: number;
  readonly enabledCount: number;
  readonly apiKeyStatus: ApiKeyStatus;
  readonly healthStatus: ProviderCheckStatus | null;
  readonly lastCheckedAt: string | null;
  readonly latencyMs: number | null;
}

export interface ProviderOverview {
  readonly rows: ReadonlyArray<ProviderOverviewRow>;
  readonly totalCount: number;
  readonly readyCount: number;
  readonly healthyCount: number;
}

function latestHealthByProvider(
  matrix: ProviderMatrix,
): ReadonlyMap<string, ProviderMatrixCell> {
  const latest: Map<string, ProviderMatrixCell> = new Map();
  for (const cell of matrix.cells) {
    const existing = latest.get(cell.provider);
    if (existing === undefined || cell.at > existing.at) {
      latest.set(cell.provider, cell);
    }
  }
  return latest;
}

export function buildProviderOverview(
  sources: ReadonlyArray<DataSourceEntry>,
  matrix: ProviderMatrix,
): ProviderOverview {
  const health = latestHealthByProvider(matrix);
  const order: string[] = [];
  const byProvider: Map<string, DataSourceEntry[]> = new Map();
  for (const source of sources) {
    const existing = byProvider.get(source.provider);
    if (existing === undefined) {
      byProvider.set(source.provider, [source]);
      order.push(source.provider);
    } else {
      existing.push(source);
    }
  }
  const rows: ProviderOverviewRow[] = order.map((provider) => {
    const providerSources = byProvider.get(provider) ?? [];
    const first = providerSources[0];
    const cell = health.get(provider);
    return {
      provider,
      sourceCount: providerSources.length,
      enabledCount: providerSources.filter((source) => source.settings.enabled)
        .length,
      apiKeyStatus: first?.api_key_status ?? "n/a",
      healthStatus: cell?.status ?? null,
      lastCheckedAt: cell?.at ?? null,
      latencyMs: cell?.latency_ms ?? null,
    };
  });
  return {
    rows,
    totalCount: rows.length,
    readyCount: rows.filter((row) => row.apiKeyStatus !== "missing").length,
    healthyCount: rows.filter((row) => row.healthStatus === "success").length,
  };
}
