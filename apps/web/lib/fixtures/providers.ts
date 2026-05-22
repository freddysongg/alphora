import type { StatusPillStatus } from "@/components/ui";

export type ProviderId =
  | "yfinance"
  | "alphavantage"
  | "yahoo-news"
  | "stocktwits"
  | "reddit"
  | "polygon";

export type ToolId =
  | "price"
  | "indicators"
  | "fundamentals"
  | "news"
  | "insider"
  | "sentiment";

export interface ProviderRow {
  id: ProviderId;
  label: string;
}

export interface ToolColumn {
  id: ToolId;
  label: string;
}

export interface MatrixCell {
  status: StatusPillStatus;
  lastFetch: string;
  samples: number;
  latencyMs: number;
}

export const providerRows: readonly ProviderRow[] = [
  { id: "yfinance", label: "yfinance" },
  { id: "alphavantage", label: "Alpha Vantage" },
  { id: "yahoo-news", label: "Yahoo Finance News" },
  { id: "stocktwits", label: "StockTwits" },
  { id: "reddit", label: "Reddit" },
  { id: "polygon", label: "Polygon (future)" },
] as const;

export const toolColumns: readonly ToolColumn[] = [
  { id: "price", label: "Price" },
  { id: "indicators", label: "Indicators" },
  { id: "fundamentals", label: "Fundamentals" },
  { id: "news", label: "News" },
  { id: "insider", label: "Insider" },
  { id: "sentiment", label: "Sentiment" },
] as const;

export type ProviderMatrix = Record<
  ProviderId,
  Record<ToolId, MatrixCell | null>
>;

export const providerMatrix: ProviderMatrix = {
  yfinance: {
    price: {
      status: "succeeded",
      lastFetch: "2026-05-16T14:32:02Z",
      samples: 1820,
      latencyMs: 412,
    },
    indicators: {
      status: "succeeded",
      lastFetch: "2026-05-16T14:32:03Z",
      samples: 1820,
      latencyMs: 484,
    },
    fundamentals: {
      status: "succeeded",
      lastFetch: "2026-05-16T14:31:50Z",
      samples: 240,
      latencyMs: 728,
    },
    news: null,
    insider: {
      status: "paused",
      lastFetch: "2026-05-15T22:14:00Z",
      samples: 18,
      latencyMs: 1240,
    },
    sentiment: null,
  },
  alphavantage: {
    price: {
      status: "succeeded",
      lastFetch: "2026-05-16T14:32:08Z",
      samples: 1820,
      latencyMs: 612,
    },
    indicators: {
      status: "succeeded",
      lastFetch: "2026-05-16T14:32:09Z",
      samples: 1820,
      latencyMs: 558,
    },
    fundamentals: {
      status: "succeeded",
      lastFetch: "2026-05-16T14:31:42Z",
      samples: 240,
      latencyMs: 894,
    },
    news: null,
    insider: {
      status: "failed",
      lastFetch: "2026-05-16T14:32:11Z",
      samples: 0,
      latencyMs: 5021,
    },
    sentiment: null,
  },
  "yahoo-news": {
    price: null,
    indicators: null,
    fundamentals: null,
    news: {
      status: "succeeded",
      lastFetch: "2026-05-16T14:32:03Z",
      samples: 142,
      latencyMs: 687,
    },
    insider: null,
    sentiment: {
      status: "succeeded",
      lastFetch: "2026-05-16T14:32:04Z",
      samples: 142,
      latencyMs: 218,
    },
  },
  stocktwits: {
    price: null,
    indicators: null,
    fundamentals: null,
    news: null,
    insider: null,
    sentiment: {
      status: "paused",
      lastFetch: "2026-05-16T13:58:00Z",
      samples: 412,
      latencyMs: 824,
    },
  },
  reddit: {
    price: null,
    indicators: null,
    fundamentals: null,
    news: {
      status: "succeeded",
      lastFetch: "2026-05-16T14:32:04Z",
      samples: 36,
      latencyMs: 1018,
    },
    insider: null,
    sentiment: {
      status: "succeeded",
      lastFetch: "2026-05-16T14:32:05Z",
      samples: 36,
      latencyMs: 1142,
    },
  },
  polygon: {
    price: { status: "pending", lastFetch: "—", samples: 0, latencyMs: 0 },
    indicators: { status: "pending", lastFetch: "—", samples: 0, latencyMs: 0 },
    fundamentals: {
      status: "pending",
      lastFetch: "—",
      samples: 0,
      latencyMs: 0,
    },
    news: null,
    insider: null,
    sentiment: null,
  },
};

export interface RecentCall {
  ts: string;
  ticker: string;
  latencyMs: number;
  status: StatusPillStatus;
  error: string | null;
}

export const sampleRecentCalls: readonly RecentCall[] = [
  {
    ts: "14:32:02.418",
    ticker: "AAPL",
    latencyMs: 412,
    status: "succeeded",
    error: null,
  },
  {
    ts: "14:31:48.122",
    ticker: "NVDA",
    latencyMs: 387,
    status: "succeeded",
    error: null,
  },
  {
    ts: "14:31:32.918",
    ticker: "TSLA",
    latencyMs: 528,
    status: "succeeded",
    error: null,
  },
  {
    ts: "14:31:18.402",
    ticker: "META",
    latencyMs: 391,
    status: "succeeded",
    error: null,
  },
  {
    ts: "14:30:54.218",
    ticker: "GOOGL",
    latencyMs: 442,
    status: "succeeded",
    error: null,
  },
  {
    ts: "14:30:32.018",
    ticker: "MSFT",
    latencyMs: 5021,
    status: "failed",
    error: "upstream timeout",
  },
  {
    ts: "14:30:12.812",
    ticker: "AMZN",
    latencyMs: 418,
    status: "succeeded",
    error: null,
  },
  {
    ts: "14:29:48.428",
    ticker: "AMD",
    latencyMs: 467,
    status: "succeeded",
    error: null,
  },
] as const;

export const sampleResponseJson = `{
  "ticker": "AAPL",
  "asOf": "2026-05-16T14:32:02Z",
  "price": 212.45,
  "previousClose": 209.48,
  "dayChangePct": 1.42,
  "volume": 48201842,
  "indicators": {
    "rsi14": 62.18,
    "macd": 1.84,
    "sma50": 198.21,
    "sma200": 184.62
  },
  "provenance": {
    "provider": "yfinance",
    "tool": "price",
    "samples": 1820,
    "latencyMs": 412
  }
}`;
