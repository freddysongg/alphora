"use client";

import type { ReactElement } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import type { ColumnDef } from "@tanstack/react-table";
import { Badge, DataTable, StatusPill } from "@/components/ui";
import type { BadgeVariant } from "@/components/ui";
import type { components } from "@/lib/api";
import { centsToDollars } from "@/lib/format/cents";
import { runStatusToStatusKind } from "@/lib/research/status-mapping";

type ResearchRunSummary = components["schemas"]["ResearchRunSummary"];
type PaperPositionPublic = components["schemas"]["PaperPositionPublic"];
type FinalRating = NonNullable<ResearchRunSummary["final_rating"]>;

const DASH = "—";
const ISO_DATE_LENGTH = 10;

const ratingToBadge: Record<FinalRating, BadgeVariant> = {
  buy: "buy",
  hold: "hold",
  sell: "sell",
  none: "none",
};

function resolveBadgeVariant(
  rating: ResearchRunSummary["final_rating"],
): BadgeVariant {
  if (rating === null) {
    return "none";
  }
  return ratingToBadge[rating];
}

function formatIsoDate(iso: string): string {
  if (typeof iso !== "string" || iso.length < ISO_DATE_LENGTH) {
    return DASH;
  }
  const datePart = iso.slice(0, ISO_DATE_LENGTH);
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return DASH;
  }
  return datePart;
}

const historicalColumns: ColumnDef<ResearchRunSummary, unknown>[] = [
  {
    accessorKey: "created_at",
    header: "Date",
    cell: ({ getValue }) => (
      <span className="font-mono text-fg">
        {formatIsoDate(String(getValue<string>()))}
      </span>
    ),
  },
  {
    accessorKey: "final_rating",
    header: "Rating",
    cell: ({ getValue }) => (
      <Badge
        variant={resolveBadgeVariant(
          getValue<ResearchRunSummary["final_rating"]>(),
        )}
      />
    ),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ getValue }) => (
      <StatusPill
        status={runStatusToStatusKind(getValue<ResearchRunSummary["status"]>())}
      />
    ),
  },
  {
    id: "tokens",
    header: "Tokens",
    meta: { numeric: true },
    cell: () => <span className="text-fg-subtle">{DASH}</span>,
  },
];

export interface HistoricalRunsTableProps {
  runs: readonly ResearchRunSummary[];
}

export function HistoricalRunsTable(
  props: HistoricalRunsTableProps,
): ReactElement {
  const { runs } = props;
  const router = useRouter();
  return (
    <DataTable<ResearchRunSummary>
      data={[...runs]}
      columns={historicalColumns}
      getRowId={(row) => row.id}
      emptyState="No runs for this ticker yet."
      onRowClick={(row) => router.push(`/research/runs/${row.id}` as Route)}
    />
  );
}

interface LinkedPositionRow {
  id: string;
  account: string;
  quantity: number;
  avgCostCents: number;
}

const linkedColumns: ColumnDef<LinkedPositionRow, unknown>[] = [
  {
    accessorKey: "account",
    header: "Account",
    cell: ({ getValue }) => (
      <span className="text-fg">{String(getValue<string>())}</span>
    ),
  },
  {
    accessorKey: "quantity",
    header: "Qty",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{getValue<number>().toLocaleString()}</span>,
  },
  {
    accessorKey: "avgCostCents",
    header: "Avg Cost",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{centsToDollars(getValue<number>())}</span>,
  },
  {
    id: "mark",
    header: "Mark",
    meta: { numeric: true },
    cell: () => <span className="text-fg-subtle">{DASH}</span>,
  },
  {
    id: "pl",
    header: "P/L",
    meta: { numeric: true },
    cell: () => <span className="text-fg-subtle">{DASH}</span>,
  },
];

export interface LinkedPositionsTableProps {
  positions: readonly PaperPositionPublic[];
  portfolioName: string;
}

export function LinkedPositionsTable(
  props: LinkedPositionsTableProps,
): ReactElement {
  const { positions, portfolioName } = props;
  const rows: LinkedPositionRow[] = positions.map((position) => ({
    id: position.id,
    account: portfolioName,
    quantity: position.quantity,
    avgCostCents: position.avg_cost_cents,
  }));
  return (
    <DataTable<LinkedPositionRow>
      data={rows}
      columns={linkedColumns}
      getRowId={(row) => row.id}
      emptyState="No paper positions in this ticker."
    />
  );
}
