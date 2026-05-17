"use client";

import type { ReactElement } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/ui";
import type { TickerRow } from "@/lib/fixtures/tickers";
import { cn } from "@/lib/cn";

function formatPrice(value: number): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatDayPct(value: number): string {
  const prefix = value >= 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)}%`;
}

const columns: ColumnDef<TickerRow, unknown>[] = [
  {
    accessorKey: "ticker",
    header: "Ticker",
    cell: ({ getValue }) => (
      <span className="font-mono text-fg">{String(getValue<string>())}</span>
    ),
  },
  {
    accessorKey: "name",
    header: "Name",
    cell: ({ getValue }) => (
      <span className="text-fg-muted">{String(getValue<string>())}</span>
    ),
  },
  {
    accessorKey: "price",
    header: "Price",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{formatPrice(getValue<number>())}</span>,
  },
  {
    accessorKey: "dayPct",
    header: "Day %",
    meta: { numeric: true },
    cell: ({ getValue }) => {
      const dayPct = getValue<number>();
      return (
        <span
          className={cn(
            dayPct >= 0 ? "text-accent-text" : "text-danger",
          )}
        >
          {formatDayPct(dayPct)}
        </span>
      );
    },
  },
  {
    accessorKey: "sector",
    header: "Sector",
    cell: ({ getValue }) => (
      <span className="text-fg-muted">{String(getValue<string>())}</span>
    ),
  },
];

export interface CompaniesTableProps {
  rows: readonly TickerRow[];
}

export function CompaniesTable(props: CompaniesTableProps): ReactElement {
  const { rows } = props;
  const router = useRouter();
  return (
    <DataTable<TickerRow>
      data={[...rows]}
      columns={columns}
      getRowId={(row) => row.ticker}
      onRowClick={(row) =>
        router.push(`/markets/companies/${row.ticker}` as Route)
      }
    />
  );
}
