import { describe, expect, test } from "vitest";
import { groupForProviderSerialization } from "@/lib/data-health/test-pull-client";
import type { DataSourceEntry } from "@/lib/data-health/types";

function makeEntry(key: string, provider: string): DataSourceEntry {
  return {
    key,
    provider,
    label: key,
    caption: "",
    scope: "ticker",
    default_lookback_days: 30,
    api_key_env: null,
    api_key_status: "configured",
    preview_columns: [],
    settings: {
      enabled: true,
      lookback_days: null,
      notes: null,
      updated_at: null,
    },
  };
}

describe("groupForProviderSerialization", () => {
  test("groups by provider preserving registry order", () => {
    const entries = [
      makeEntry("finnhub_news", "finnhub"),
      makeEntry("polygon_aggregates", "polygon"),
      makeEntry("finnhub_profile", "finnhub"),
    ];
    const groups = groupForProviderSerialization(entries);
    expect(groups).toEqual([
      { provider: "finnhub", sources: [entries[0], entries[2]] },
      { provider: "polygon", sources: [entries[1]] },
    ]);
  });
});
