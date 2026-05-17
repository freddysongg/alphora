"use client";

import type { ReactElement } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable, StatusDot } from "@/components/ui";
import {
  getOrderStatusDot,
  sampleOrders,
} from "@/lib/fixtures/portfolio";
import type { OrderRow, OrderSide, OrderType } from "@/lib/fixtures/portfolio";

const sideLabels: Record<OrderSide, string> = {
  buy: "BUY",
  sell: "SELL",
};

const typeLabels: Record<OrderType, string> = {
  market: "MARKET",
};

const columns: ColumnDef<OrderRow, unknown>[] = [
  {
    accessorKey: "ts",
    header: "Time",
    cell: ({ getValue }) => (
      <span className="font-mono text-fg-muted">{String(getValue<string>())}</span>
    ),
  },
  {
    accessorKey: "ticker",
    header: "Ticker",
    cell: ({ getValue }) => (
      <span className="font-mono text-fg">{String(getValue<string>())}</span>
    ),
  },
  {
    accessorKey: "side",
    header: "Side",
    cell: ({ getValue }) => (
      <span className="text-fg">{sideLabels[getValue<OrderSide>()]}</span>
    ),
  },
  {
    accessorKey: "qty",
    header: "Qty",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{getValue<number>().toLocaleString()}</span>,
  },
  {
    accessorKey: "type",
    header: "Type",
    cell: ({ getValue }) => (
      <span className="text-fg-muted">{typeLabels[getValue<OrderType>()]}</span>
    ),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusDot status={getOrderStatusDot(row.original.status)} />,
  },
];

export function OrdersTable(): ReactElement {
  return (
    <DataTable<OrderRow>
      data={[...sampleOrders]}
      columns={columns}
      getRowId={(row) => row.id}
    />
  );
}
