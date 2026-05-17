"use client";

import type { ReactElement } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { DataTable } from "@/components/ui";
import type { components } from "@/lib/api";
import { centsToDollars } from "@/lib/format/cents";

type PaperPositionPublic = components["schemas"]["PaperPositionPublic"];

const FALLBACK = "—";

function formatSignedDollars(cents: number): string {
  const prefix = cents >= 0 ? "+" : "-";
  return `${prefix}${centsToDollars(Math.abs(cents))}`;
}

function formatSignedPct(value: number): string {
  const prefix = value >= 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)}%`;
}

function toneClass(cents: number): string {
  if (cents > 0) {
    return "text-accent-text";
  }
  if (cents < 0) {
    return "text-danger";
  }
  return "text-fg";
}

const columns: ColumnDef<PaperPositionPublic, unknown>[] = [
  {
    accessorKey: "ticker",
    header: "Ticker",
    cell: ({ getValue }) => (
      <span className="font-mono text-fg">{String(getValue<string>())}</span>
    ),
  },
  {
    accessorKey: "quantity",
    header: "Qty",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{getValue<number>().toLocaleString()}</span>,
  },
  {
    accessorKey: "avg_cost_cents",
    header: "Avg Cost",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{centsToDollars(getValue<number>())}</span>,
  },
  {
    accessorKey: "mark_cents",
    header: "Mark",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{centsToDollars(getValue<number>())}</span>,
  },
  {
    id: "market_value",
    header: "Mkt Value",
    meta: { numeric: true },
    cell: ({ row }) => {
      const { quantity, mark_cents } = row.original;
      return <span>{centsToDollars(quantity * mark_cents)}</span>;
    },
  },
  {
    id: "unrealized_pl",
    header: "Unrealized P/L",
    meta: { numeric: true },
    cell: ({ row }) => {
      const { quantity, mark_cents, avg_cost_cents } = row.original;
      const plCents = quantity * (mark_cents - avg_cost_cents);
      return (
        <span className={toneClass(plCents)}>{formatSignedDollars(plCents)}</span>
      );
    },
  },
  {
    id: "pct_change",
    header: "% Change",
    meta: { numeric: true },
    cell: ({ row }) => {
      const { mark_cents, avg_cost_cents } = row.original;
      if (avg_cost_cents === 0) {
        return <span className="text-fg-subtle">{FALLBACK}</span>;
      }
      const pct = ((mark_cents - avg_cost_cents) / avg_cost_cents) * 100;
      const pctCentsForTone = mark_cents - avg_cost_cents;
      return (
        <span className={toneClass(pctCentsForTone)}>
          {formatSignedPct(pct)}
        </span>
      );
    },
  },
];

export interface PositionsTableProps {
  rows: readonly PaperPositionPublic[];
}

export function PositionsTable(props: PositionsTableProps): ReactElement {
  const { rows } = props;
  return (
    <DataTable<PaperPositionPublic>
      data={[...rows]}
      columns={columns}
      getRowId={(row) => row.id}
      emptyState="No open positions."
    />
  );
}
