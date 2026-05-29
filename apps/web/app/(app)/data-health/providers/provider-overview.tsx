import Link from "next/link";
import type { ReactElement } from "react";
import { StatusPill } from "@/components/ui";
import type {
  ProviderOverview,
  ProviderOverviewRow,
} from "@/lib/data-health/overview";
import { providerCheckStatusToStatusKind } from "@/lib/data-health/status";
import { formatDateTime } from "@/lib/format/date-time";

const COLUMN_HEADERS: ReadonlyArray<string> = [
  "Provider",
  "Feeds",
  "API Key",
  "Enabled",
  "Health",
  "Last checked",
  "Latency",
];

export interface ProviderOverviewTableProps {
  readonly overview: ProviderOverview;
}

function renderApiKey(
  status: ProviderOverviewRow["apiKeyStatus"],
): ReactElement {
  if (status === "missing") {
    return (
      <Link href="/settings/api-keys" className="text-danger text-xs underline">
        ✗ missing
      </Link>
    );
  }
  if (status === "configured") {
    return <span className="text-fg text-xs">✓ configured</span>;
  }
  return <span className="text-fg-subtle text-xs">n/a</span>;
}

function renderHealth(row: ProviderOverviewRow): ReactElement {
  if (row.healthStatus === null) {
    return <span className="text-fg-subtle text-xs">not checked</span>;
  }
  return (
    <StatusPill
      status={providerCheckStatusToStatusKind(row.healthStatus)}
      label={row.healthStatus}
    />
  );
}

export function ProviderOverviewTable(
  props: ProviderOverviewTableProps,
): ReactElement {
  const { overview } = props;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2 text-xs text-fg-muted">
        <span className="rounded-md border border-line px-2 py-1">
          {overview.totalCount} providers
        </span>
        <span className="rounded-md border border-line px-2 py-1">
          {overview.readyCount} ready
        </span>
        <span className="rounded-md border border-line px-2 py-1">
          {overview.healthyCount} healthy
        </span>
      </div>
      <div className="overflow-x-auto border border-line rounded-md">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line">
              {COLUMN_HEADERS.map((head) => (
                <th
                  key={head}
                  scope="col"
                  className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted py-2 px-3 text-left"
                >
                  {head}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {overview.rows.map((row) => (
              <tr
                key={row.provider}
                className="border-b border-line/60 hover:bg-surface-2 transition-colors duration-150"
              >
                <td className="py-3 px-3 text-fg">{row.provider}</td>
                <td className="py-3 px-3 text-fg-muted">{row.sourceCount}</td>
                <td className="py-3 px-3">{renderApiKey(row.apiKeyStatus)}</td>
                <td className="py-3 px-3 text-fg-muted">
                  {row.enabledCount}/{row.sourceCount}
                </td>
                <td className="py-3 px-3">{renderHealth(row)}</td>
                <td className="py-3 px-3 text-fg-muted">
                  {row.lastCheckedAt !== null
                    ? formatDateTime(row.lastCheckedAt)
                    : "—"}
                </td>
                <td className="py-3 px-3 text-fg-muted">
                  {row.latencyMs !== null ? `${row.latencyMs}ms` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
