"use client";

import type { ReactElement } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/ui";

export interface CompanyRow {
  ticker: string;
}

const DASH = "—";

const columns: ColumnDef<CompanyRow, unknown>[] = [
  {
    accessorKey: "ticker",
    header: "Ticker",
    cell: ({ getValue }) => (
      <span className="font-mono text-fg">{String(getValue<string>())}</span>
    ),
  },
  {
    id: "name",
    header: "Name",
    cell: () => <span className="text-fg-subtle">{DASH}</span>,
  },
  {
    id: "price",
    header: "Price",
    meta: { numeric: true },
    cell: () => <span className="text-fg-subtle">{DASH}</span>,
  },
  {
    id: "dayPct",
    header: "Day %",
    meta: { numeric: true },
    cell: () => <span className="text-fg-subtle">{DASH}</span>,
  },
  {
    id: "sector",
    header: "Sector",
    cell: () => <span className="text-fg-subtle">{DASH}</span>,
  },
];

const emptyState = "No companies yet. Create a research run to populate this list.";

export interface CompaniesTableProps {
  rows: readonly CompanyRow[];
}

export function CompaniesTable(props: CompaniesTableProps): ReactElement {
  const { rows } = props;
  const router = useRouter();
  return (
    <DataTable<CompanyRow>
      data={[...rows]}
      columns={columns}
      getRowId={(row) => row.ticker}
      emptyState={emptyState}
      onRowClick={(row) =>
        router.push(`/markets/companies/${row.ticker}` as Route)
      }
    />
  );
}
