import { describe, expect, test } from "vitest";
import { PREVIEW_COLUMNS } from "@/app/(app)/data-health/sources/preview-columns";

describe("PREVIEW_COLUMNS", () => {
  test("has an entry for finnhub_news", () => {
    expect(PREVIEW_COLUMNS.get("finnhub_news")).toEqual([
      { key: "headline", label: "Headline" },
      { key: "source", label: "Source" },
      { key: "published_at", label: "Published" },
    ]);
  });

  test("covers all 17 registry keys", () => {
    const expected = [
      "finnhub_insider_transactions",
      "finnhub_news",
      "finnhub_peers",
      "finnhub_price_target",
      "finnhub_profile",
      "finnhub_recommendation",
      "polygon_aggregates",
      "sec_filings",
      "tiingo_news_items",
      "gdelt",
      "fred_observations",
      "fed_press",
      "cme_fedwatch",
      "kalshi_markets",
      "polymarket_events",
      "polymarket_price_history",
      "congress_bills",
    ];
    for (const key of expected) {
      expect(PREVIEW_COLUMNS.has(key)).toBe(true);
    }
  });
});
