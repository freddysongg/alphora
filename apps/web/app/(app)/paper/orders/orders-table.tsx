"use client";

import type { ReactElement } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { DataTable, StatusPill } from "@/components/ui";
import type { components } from "@/lib/api";
import { formatDateTime } from "@/lib/format/date-time";
import { orderStatusToStatusKind } from "@/lib/paper/order-status";

type PaperOrderPublic = components["schemas"]["PaperOrderPublic"];
type OrderSide = components["schemas"]["OrderSideEnum"];
type OrderType = components["schemas"]["OrderTypeEnum"];

const sideLabels: Record<OrderSide, string> = {
  buy: "BUY",
  sell: "SELL",
};

const typeLabels: Record<OrderType, string> = {
  market: "MARKET",
};

const columns: ColumnDef<PaperOrderPublic, unknown>[] = [
  {
    accessorKey: "submitted_at",
    header: "Time",
    cell: ({ getValue }) => (
      <span className="font-mono text-fg-muted">
        {formatDateTime(getValue<string>())}
      </span>
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
    accessorKey: "quantity",
    header: "Qty",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{getValue<number>().toLocaleString()}</span>,
  },
  {
    accessorKey: "order_type",
    header: "Type",
    cell: ({ getValue }) => (
      <span className="text-fg-muted">{typeLabels[getValue<OrderType>()]}</span>
    ),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <StatusPill status={orderStatusToStatusKind(row.original.status)} />
    ),
  },
];

export interface OrdersTableProps {
  rows: readonly PaperOrderPublic[];
}

export function OrdersTable(props: OrdersTableProps): ReactElement {
  const { rows } = props;
  return (
    <DataTable<PaperOrderPublic>
      data={[...rows]}
      columns={columns}
      getRowId={(row) => row.id}
      emptyState="No orders yet."
    />
  );
}
