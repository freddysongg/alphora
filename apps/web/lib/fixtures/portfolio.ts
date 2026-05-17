import type { StatusKind } from "@/components/ui/status-dot";

export interface PortfolioPosition {
  ticker: string;
  qty: number;
  avgCost: number;
  mark: number;
  marketValue: number;
  unrealizedPl: number;
  pctChange: number;
}

export const samplePositions: readonly PortfolioPosition[] = [
  {
    ticker: "AAPL",
    qty: 142,
    avgCost: 184.21,
    mark: 212.45,
    marketValue: 30167.9,
    unrealizedPl: 4010.08,
    pctChange: 15.33,
  },
  {
    ticker: "NVDA",
    qty: 60,
    avgCost: 412.18,
    mark: 475.12,
    marketValue: 28507.2,
    unrealizedPl: 3776.4,
    pctChange: 15.27,
  },
  {
    ticker: "MSFT",
    qty: 80,
    avgCost: 395.72,
    mark: 421.55,
    marketValue: 33724.0,
    unrealizedPl: 2066.4,
    pctChange: 6.53,
  },
  {
    ticker: "GOOGL",
    qty: 124,
    avgCost: 168.18,
    mark: 174.92,
    marketValue: 21690.08,
    unrealizedPl: 835.76,
    pctChange: 4.01,
  },
  {
    ticker: "META",
    qty: 32,
    avgCost: 478.41,
    mark: 502.18,
    marketValue: 16069.76,
    unrealizedPl: 760.64,
    pctChange: 4.97,
  },
  {
    ticker: "AMD",
    qty: 90,
    avgCost: 178.42,
    mark: 165.82,
    marketValue: 14923.8,
    unrealizedPl: -1134.0,
    pctChange: -7.06,
  },
  {
    ticker: "AMZN",
    qty: 70,
    avgCost: 172.18,
    mark: 188.27,
    marketValue: 13178.9,
    unrealizedPl: 1126.3,
    pctChange: 9.34,
  },
  {
    ticker: "JPM",
    qty: 120,
    avgCost: 205.42,
    mark: 218.34,
    marketValue: 26200.8,
    unrealizedPl: 1550.4,
    pctChange: 6.29,
  },
] as const;

export interface PortfolioSummary {
  cash: number;
  equity: number;
  dayPl: number;
  allTimePl: number;
  vsSpyPct: number;
}

export const samplePortfolioSummary: PortfolioSummary = {
  cash: 12438.51,
  equity: 184022.1,
  dayPl: 2341.99,
  allTimePl: 24118.4,
  vsSpyPct: 3.18,
};

export type OrderSide = "buy" | "sell";
export type OrderType = "market";
export type OrderStatus = "filled" | "pending" | "cancelled" | "rejected";

export interface OrderRow {
  id: string;
  ts: string;
  ticker: string;
  side: OrderSide;
  qty: number;
  type: OrderType;
  status: OrderStatus;
}

const orderStatusToDot: Record<OrderStatus, StatusKind> = {
  filled: "succeeded",
  pending: "pending",
  cancelled: "stale",
  rejected: "failed",
};

export function getOrderStatusDot(status: OrderStatus): StatusKind {
  return orderStatusToDot[status];
}

export const sampleOrders: readonly OrderRow[] = [
  {
    id: "ord-1a2b3c4d5e6f",
    ts: "2026-05-16T14:18:42Z",
    ticker: "AAPL",
    side: "buy",
    qty: 24,
    type: "market",
    status: "filled",
  },
  {
    id: "ord-2b3c4d5e6f7g",
    ts: "2026-05-16T13:54:18Z",
    ticker: "NVDA",
    side: "buy",
    qty: 12,
    type: "market",
    status: "filled",
  },
  {
    id: "ord-3c4d5e6f7g8h",
    ts: "2026-05-16T12:42:31Z",
    ticker: "MSFT",
    side: "buy",
    qty: 18,
    type: "market",
    status: "filled",
  },
  {
    id: "ord-4d5e6f7g8h9i",
    ts: "2026-05-16T11:18:02Z",
    ticker: "AMD",
    side: "buy",
    qty: 30,
    type: "market",
    status: "filled",
  },
  {
    id: "ord-5e6f7g8h9i0j",
    ts: "2026-05-16T10:54:11Z",
    ticker: "TSLA",
    side: "buy",
    qty: 8,
    type: "market",
    status: "rejected",
  },
  {
    id: "ord-6f7g8h9i0j1k",
    ts: "2026-05-16T10:18:42Z",
    ticker: "GOOGL",
    side: "buy",
    qty: 14,
    type: "market",
    status: "filled",
  },
  {
    id: "ord-7g8h9i0j1k2l",
    ts: "2026-05-16T09:48:18Z",
    ticker: "META",
    side: "buy",
    qty: 6,
    type: "market",
    status: "filled",
  },
  {
    id: "ord-8h9i0j1k2l3m",
    ts: "2026-05-16T09:32:08Z",
    ticker: "AMZN",
    side: "buy",
    qty: 10,
    type: "market",
    status: "pending",
  },
] as const;
