import type { components } from "@/lib/api";

export type DataSourceEntry = components["schemas"]["DataSourceEntryPublic"];
export type DataSourceList = components["schemas"]["DataSourceList"];
export type DataSourceSettings = components["schemas"]["DataSourceSettingsPublic"];
export type DataSourceSettingsUpdate =
  components["schemas"]["DataSourceSettingsUpdate"];
export type DataSourceScope = DataSourceEntry["scope"];
export type ApiKeyStatus = DataSourceEntry["api_key_status"];
export type TestPullRequest = components["schemas"]["DataSourceTestPullRequest"];
export type TestPullResponse = components["schemas"]["DataSourceTestPullResponse"];
export type TestPullStatus = TestPullResponse["status"];

export interface SourcesByProvider {
  readonly provider: string;
  readonly sources: ReadonlyArray<DataSourceEntry>;
}

export function groupSourcesByProvider(
  sources: ReadonlyArray<DataSourceEntry>,
): ReadonlyArray<SourcesByProvider> {
  const order: string[] = [];
  const byProvider: Map<string, DataSourceEntry[]> = new Map();
  for (const source of sources) {
    const existing = byProvider.get(source.provider);
    if (existing === undefined) {
      const list: DataSourceEntry[] = [source];
      byProvider.set(source.provider, list);
      order.push(source.provider);
    } else {
      existing.push(source);
    }
  }
  return order.map((provider) => ({
    provider,
    sources: byProvider.get(provider) ?? [],
  }));
}
