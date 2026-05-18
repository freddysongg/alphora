"use client";

import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { CapsLabel, DataTable, StatusDot } from "@/components/ui";
import { getBrowserApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { providerCheckStatusToStatusKind } from "@/lib/data-health/status";
import { formatDateTime } from "@/lib/format/date-time";

type ProviderCheckPublic = components["schemas"]["ProviderCheckPublic"];

type FetchState =
  | { kind: "loading" }
  | { kind: "ready"; calls: readonly ProviderCheckPublic[] }
  | { kind: "error"; detail: string };

const CALL_LIMIT = 20;

const SAMPLE_RESPONSE_CAPTION = "Sample response not stored yet.";
const GENERIC_FETCH_ERROR = "Failed to load recent calls.";

const callsColumns: ColumnDef<ProviderCheckPublic, unknown>[] = [
  {
    accessorKey: "at",
    header: "Time",
    cell: ({ getValue }) => (
      <span className="font-mono text-fg-muted">
        {formatDateTime(String(getValue<string>()))}
      </span>
    ),
  },
  {
    accessorKey: "ticker",
    header: "Ticker",
    cell: ({ getValue }) => {
      const ticker = getValue<string | null>();
      return ticker ? (
        <span className="font-mono text-fg">{ticker}</span>
      ) : (
        <span className="text-xs text-fg-subtle">—</span>
      );
    },
  },
  {
    accessorKey: "latency_ms",
    header: "Latency",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{getValue<number>().toLocaleString()}</span>,
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ getValue }) => {
      const raw = getValue<ProviderCheckPublic["status"]>();
      return (
        <StatusDot status={providerCheckStatusToStatusKind(raw)} label={raw} />
      );
    },
  },
  {
    accessorKey: "error_message",
    header: "Error",
    cell: ({ getValue }) => {
      const message = getValue<string | null>();
      return message ? (
        <span className="text-xs text-danger">{message}</span>
      ) : (
        <span className="text-xs text-fg-subtle">—</span>
      );
    },
  },
];

export interface ProviderCellRailProps {
  provider: string;
  tool: string;
}

function CallsSkeleton(): ReactElement {
  return (
    <div className="flex flex-col gap-2" aria-busy="true" aria-live="polite">
      {Array.from({ length: 4 }).map((_, index) => (
        <div
          key={index}
          className="h-6 rounded-md border border-line/60 bg-surface"
        />
      ))}
    </div>
  );
}

function cellKey(provider: string, tool: string): string {
  return `${provider}::${tool}`;
}

export function ProviderCellRail(
  props: ProviderCellRailProps,
): ReactElement {
  const { provider, tool } = props;
  const activeKey = cellKey(provider, tool);
  const [state, setState] = useState<FetchState>({ kind: "loading" });
  const [stateKey, setStateKey] = useState<string>(activeKey);

  if (stateKey !== activeKey) {
    setStateKey(activeKey);
    setState({ kind: "loading" });
  }

  useEffect(() => {
    const controller = new AbortController();
    let isCancelled = false;

    async function fetchCalls(): Promise<void> {
      try {
        const { data } = await getBrowserApi().GET("/api/data-health/calls", {
          params: { query: { provider, tool, limit: CALL_LIMIT } },
          signal: controller.signal,
        });
        if (isCancelled) {
          return;
        }
        setState({ kind: "ready", calls: data ?? [] });
      } catch (caught) {
        if (isCancelled || controller.signal.aborted) {
          return;
        }
        if (isApiError(caught)) {
          setState({ kind: "error", detail: caught.detail });
          return;
        }
        console.error("Failed to load provider calls", caught);
        setState({ kind: "error", detail: GENERIC_FETCH_ERROR });
      }
    }

    void fetchCalls();

    return (): void => {
      isCancelled = true;
      controller.abort();
    };
  }, [provider, tool]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <CapsLabel>PROVIDER · TOOL</CapsLabel>
        <span className="font-mono text-sm text-fg">
          {provider} / {tool}
        </span>
      </div>
      <div className="flex flex-col gap-2">
        <CapsLabel>RECENT CALLS</CapsLabel>
        {state.kind === "loading" ? (
          <CallsSkeleton />
        ) : state.kind === "error" ? (
          <div
            role="alert"
            className="rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            Failed to load calls: {state.detail}
          </div>
        ) : (
          <DataTable<ProviderCheckPublic>
            data={[...state.calls]}
            columns={callsColumns}
            getRowId={(row) => row.id}
            emptyState="No recent calls."
          />
        )}
      </div>
      <div className="flex flex-col gap-2">
        <CapsLabel>SAMPLE RESPONSE</CapsLabel>
        <p className="text-fg-subtle text-xs">{SAMPLE_RESPONSE_CAPTION}</p>
      </div>
    </div>
  );
}
