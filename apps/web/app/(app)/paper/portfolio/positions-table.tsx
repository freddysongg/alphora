"use client";

import type { ReactElement } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/ui";
import type { PortfolioPosition } from "@/lib/fixtures/portfolio";

function formatMoney(value: number): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatPct(value: number): string {
  const prefix = value >= 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)}%`;
}

const columns: ColumnDef<PortfolioPosition, unknown>[] = [
  {
    accessorKey: "ticker",
    header: "Ticker",
    cell: ({ getValue }) => (
      <span className="font-mono text-fg">{String(getValue<string>())}</span>
    ),
  },
  {
    accessorKey: "qty",
    header: "Qty",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{getValue<number>().toLocaleString()}</span>,
  },
  {
    accessorKey: "avgCost",
    header: "Avg Cost",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{formatMoney(getValue<number>())}</span>,
  },
  {
    accessorKey: "mark",
    header: "Mark",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{formatMoney(getValue<number>())}</span>,
  },
  {
    accessorKey: "marketValue",
    header: "Mkt Value",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{formatMoney(getValue<number>())}</span>,
  },
  {
    accessorKey: "unrealizedPl",
    header: "Unrealized P/L",
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
  {
    accessorKey: "pctChange",
    header: "% Change",
    meta: { numeric: true },
    cell: ({ getValue }) => {
      const pct = getValue<number>();
      return (
        <span className={pct >= 0 ? "text-accent-text" : "text-danger"}>
          {formatPct(pct)}
        </span>
      );
    },
  },
];

export interface PositionsTableProps {
  rows: readonly PortfolioPosition[];
}

export function PositionsTable(props: PositionsTableProps): ReactElement {
  const { rows } = props;
  return (
    <DataTable<PortfolioPosition>
      data={[...rows]}
      columns={columns}
      getRowId={(row) => row.ticker}
    />
  );
}
