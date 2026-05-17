"use client";

import type { ReactElement } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import {
  CapsLabel,
  CodeBlock,
  DataTable,
  StatusDot,
} from "@/components/ui";
import type { StatusKind } from "@/components/ui";
import {
  sampleRecentCalls,
  sampleResponseJson,
} from "@/lib/fixtures/providers";
import type { RecentCall } from "@/lib/fixtures/providers";

const callsColumns: ColumnDef<RecentCall, unknown>[] = [
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
    accessorKey: "latencyMs",
    header: "Latency",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{getValue<number>().toLocaleString()}</span>,
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ getValue }) => <StatusDot status={getValue<StatusKind>()} />,
  },
  {
    accessorKey: "error",
    header: "Error",
    cell: ({ getValue }) => {
      const error = getValue<string | null>();
      return error ? (
        <span className="text-xs text-danger">{error}</span>
      ) : (
        <span className="text-xs text-fg-subtle">—</span>
      );
    },
  },
];

export interface ProviderCellRailProps {
  providerLabel: string;
  toolLabel: string;
}

export function ProviderCellRail(
  props: ProviderCellRailProps,
): ReactElement {
  const { providerLabel, toolLabel } = props;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <CapsLabel>PROVIDER · TOOL</CapsLabel>
        <span className="font-mono text-sm text-fg">
          {providerLabel} / {toolLabel}
        </span>
      </div>
      <div className="flex flex-col gap-2">
        <CapsLabel>RECENT CALLS</CapsLabel>
        <DataTable<RecentCall>
          data={[...sampleRecentCalls]}
          columns={callsColumns}
          getRowId={(row) => `${row.ts}-${row.ticker}`}
        />
      </div>
      <div className="flex flex-col gap-2">
        <CapsLabel>SAMPLE RESPONSE</CapsLabel>
        <CodeBlock lang="json">{sampleResponseJson}</CodeBlock>
      </div>
    </div>
  );
}
