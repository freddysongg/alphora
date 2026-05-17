"use client";

import type { ReactElement } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Badge, DataTable, StatusDot } from "@/components/ui";
import type { BadgeVariant, StatusKind } from "@/components/ui";

interface HistoricalRunRow {
  id: string;
  date: string;
  rating: BadgeVariant;
  status: StatusKind;
  tokens: number;
}

const historicalRuns: readonly HistoricalRunRow[] = [
  { id: "h1", date: "2026-05-16", rating: "buy", status: "succeeded", tokens: 25251 },
  { id: "h2", date: "2026-05-09", rating: "hold", status: "succeeded", tokens: 22184 },
  { id: "h3", date: "2026-05-02", rating: "buy", status: "succeeded", tokens: 24612 },
  { id: "h4", date: "2026-04-25", rating: "buy", status: "succeeded", tokens: 23018 },
  { id: "h5", date: "2026-04-18", rating: "hold", status: "succeeded", tokens: 21842 },
];

const historicalColumns: ColumnDef<HistoricalRunRow, unknown>[] = [
  { accessorKey: "date", header: "Date", cell: ({ getValue }) => <span className="font-mono text-fg">{String(getValue<string>())}</span> },
  { accessorKey: "rating", header: "Rating", cell: ({ getValue }) => <Badge variant={getValue<BadgeVariant>()} /> },
  { accessorKey: "status", header: "Status", cell: ({ getValue }) => <StatusDot status={getValue<StatusKind>()} /> },
  { accessorKey: "tokens", header: "Tokens", meta: { numeric: true }, cell: ({ getValue }) => <span>{getValue<number>().toLocaleString()}</span> },
];

export function HistoricalRunsTable(): ReactElement {
  return (
    <DataTable<HistoricalRunRow>
      data={[...historicalRuns]}
      columns={historicalColumns}
      getRowId={(row) => row.id}
    />
  );
}

interface LinkedPosition {
  id: string;
  account: string;
  qty: number;
  avgCost: number;
  mark: number;
  pl: number;
}

const linkedPositions: readonly LinkedPosition[] = [
  { id: "lp1", account: "Default", qty: 142, avgCost: 184.21, mark: 212.45, pl: 4010.08 },
  { id: "lp2", account: "Long-term", qty: 60, avgCost: 168.42, mark: 212.45, pl: 2641.8 },
];

function formatMoney(value: number): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

const linkedColumns: ColumnDef<LinkedPosition, unknown>[] = [
  { accessorKey: "account", header: "Account", cell: ({ getValue }) => <span className="text-fg">{String(getValue<string>())}</span> },
  { accessorKey: "qty", header: "Qty", meta: { numeric: true }, cell: ({ getValue }) => <span>{getValue<number>().toLocaleString()}</span> },
  { accessorKey: "avgCost", header: "Avg Cost", meta: { numeric: true }, cell: ({ getValue }) => <span>{formatMoney(getValue<number>())}</span> },
  { accessorKey: "mark", header: "Mark", meta: { numeric: true }, cell: ({ getValue }) => <span>{formatMoney(getValue<number>())}</span> },
  {
    accessorKey: "pl",
    header: "P/L",
    meta: { numeric: true },
    cell: ({ getValue }) => {
      const pl = getValue<number>();
      return (
        <span className={pl >= 0 ? "text-accent-text" : "text-danger"}>
          {pl >= 0 ? "+" : ""}
          {formatMoney(pl)}
        </span>
      );
    },
  },
];

export function LinkedPositionsTable(): ReactElement {
  return (
    <DataTable<LinkedPosition>
      data={[...linkedPositions]}
      columns={linkedColumns}
      getRowId={(row) => row.id}
    />
  );
}
