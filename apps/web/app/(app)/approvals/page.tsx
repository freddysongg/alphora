import type { Metadata } from "next";
import type { ReactElement } from "react";
import Link from "next/link";

import { CapsLabel, StatusDot } from "@/components/ui";
import type { StatusKind } from "@/components/ui";
import { listApprovals } from "@/lib/approvals/api";
import type { Approval } from "@/lib/approvals/api";
import { formatDateTime } from "@/lib/format/date-time";

export const metadata: Metadata = {
  title: "Approvals · Alphora",
};

export const dynamic = "force-dynamic";

type ApprovalStatus = Approval["status"];

const statusToKind: Record<ApprovalStatus, StatusKind> = {
  pending: "pending",
  approved: "succeeded",
  rejected: "failed",
  expired: "stale",
};

interface LoadResult {
  approvals: readonly Approval[];
  errorDetail: string | null;
}

async function loadApprovals(): Promise<LoadResult> {
  try {
    const approvals = await listApprovals({ status: "pending" });
    return { approvals, errorDetail: null };
  } catch (caught) {
    if (caught instanceof Error) {
      return { approvals: [], errorDetail: caught.message };
    }
    throw caught;
  }
}

export default async function ApprovalsPage(): Promise<ReactElement> {
  const { approvals, errorDetail } = await loadApprovals();
  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <header className="pb-6">
        <CapsLabel as="h1">APPROVALS</CapsLabel>
      </header>
      {errorDetail !== null ? (
        <div
          role="alert"
          className="mb-4 rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Failed to load approvals: {errorDetail}
        </div>
      ) : null}
      <div className="w-full overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line">
              <th
                scope="col"
                className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted py-2 px-3 text-left"
              >
                Status
              </th>
              <th
                scope="col"
                className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted py-2 px-3 text-left"
              >
                Mode
              </th>
              <th
                scope="col"
                className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted py-2 px-3 text-left"
              >
                Ticker
              </th>
              <th
                scope="col"
                className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted py-2 px-3 text-left"
              >
                Side
              </th>
              <th
                scope="col"
                className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted py-2 px-3 text-right"
              >
                Qty
              </th>
              <th
                scope="col"
                className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted py-2 px-3 text-left"
              >
                Strategy
              </th>
              <th
                scope="col"
                className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted py-2 px-3 text-left"
              >
                Decided By
              </th>
              <th
                scope="col"
                className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted py-2 px-3 text-left"
              >
                Created
              </th>
              <th scope="col" className="py-2 px-3" />
            </tr>
          </thead>
          <tbody>
            {approvals.length === 0 ? (
              <tr>
                <td
                  colSpan={9}
                  className="h-20 text-center text-fg-subtle text-sm"
                >
                  No pending approvals.
                </td>
              </tr>
            ) : (
              approvals.map((row) => (
                <tr
                  key={row.id}
                  className="h-10 border-b border-line/60 transition-colors duration-150 hover:bg-surface-2"
                >
                  <td className="px-3 text-fg">
                    <StatusDot
                      status={statusToKind[row.status]}
                      label={row.status}
                    />
                  </td>
                  <td className="px-3 text-fg-muted font-mono text-xs">
                    {row.mode}
                  </td>
                  <td className="px-3 text-fg font-mono">{row.ticker}</td>
                  <td className="px-3 text-fg">{row.side.toUpperCase()}</td>
                  <td className="px-3 text-right font-mono tabular-nums text-fg">
                    {row.qty}
                  </td>
                  <td className="px-3 text-fg-muted">{row.strategy_key}</td>
                  <td className="px-3 text-fg-muted">
                    {row.decided_by ?? "—"}
                  </td>
                  <td className="px-3 font-mono text-fg-muted">
                    {formatDateTime(row.created_at)}
                  </td>
                  <td className="px-3">
                    <Link
                      href={`/approvals/${row.id}`}
                      className="text-xs text-accent underline underline-offset-2 hover:text-accent-deep"
                    >
                      Details
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
