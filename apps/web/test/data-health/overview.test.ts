import { describe, expect, test } from "vitest";
import { buildProviderOverview } from "@/lib/data-health/overview";
import type { components } from "@/lib/api";
import type { ApiKeyStatus, DataSourceEntry } from "@/lib/data-health/types";

type ProviderMatrix = components["schemas"]["ProviderMatrix"];

interface MakeSourceOptions {
  readonly enabled?: boolean;
  readonly apiKeyStatus?: ApiKeyStatus;
}

function makeSource(
  provider: string,
  options?: MakeSourceOptions,
): DataSourceEntry {
  return {
    key: `${provider}_x`,
    provider,
    label: provider,
    caption: "",
    scope: "ticker",
    default_lookback_days: null,
    api_key_env: null,
    api_key_status: options?.apiKeyStatus ?? "configured",
    preview_columns: [],
    settings: {
      enabled: options?.enabled ?? true,
      lookback_days: null,
      notes: null,
      updated_at: null,
    },
  };
}

const EMPTY_MATRIX: ProviderMatrix = { providers: [], tools: [], cells: [] };

describe("buildProviderOverview", () => {
  test("groups sources per provider and counts feeds + enabled", () => {
    const overview = buildProviderOverview(
      [
        makeSource("finnhub"),
        makeSource("finnhub", { enabled: false }),
        makeSource("polygon"),
      ],
      EMPTY_MATRIX,
    );
    const finnhub = overview.rows.find((row) => row.provider === "finnhub");
    expect(finnhub?.sourceCount).toBe(2);
    expect(finnhub?.enabledCount).toBe(1);
    expect(overview.totalCount).toBe(2);
  });

  test("joins latest health from the matrix", () => {
    const matrix: ProviderMatrix = {
      providers: ["finnhub"],
      tools: ["health"],
      cells: [
        {
          provider: "finnhub",
          tool: "health",
          status: "success",
          at: "2026-05-28T00:00:00Z",
          latency_ms: 120,
          sample_count: 0,
          as_of: null,
        },
      ],
    };
    const overview = buildProviderOverview([makeSource("finnhub")], matrix);
    const finnhub = overview.rows.find((row) => row.provider === "finnhub");
    expect(finnhub?.healthStatus).toBe("success");
    expect(finnhub?.latencyMs).toBe(120);
    expect(overview.healthyCount).toBe(1);
  });

  test("counts ready providers as those without a missing key", () => {
    const overview = buildProviderOverview(
      [
        makeSource("finnhub", { apiKeyStatus: "missing" }),
        makeSource("sec_edgar", { apiKeyStatus: "n/a" }),
      ],
      EMPTY_MATRIX,
    );
    expect(overview.readyCount).toBe(1);
  });

  test("marks providers without a health check as not checked", () => {
    const overview = buildProviderOverview([makeSource("gdelt")], EMPTY_MATRIX);
    expect(overview.rows[0]?.healthStatus).toBeNull();
  });
});
