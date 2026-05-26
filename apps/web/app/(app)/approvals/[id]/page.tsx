import { notFound } from "next/navigation";
import type { Metadata } from "next";
import type { ReactElement } from "react";

import { CapsLabel, StatusPill } from "@/components/ui";
import type { StatusPillStatus } from "@/components/ui";
import { ApprovalActions } from "@/components/approvals/approval-actions";
import { getApproval } from "@/lib/approvals/api";
import type { ApprovalStatus } from "@/lib/approvals/api";
import { getBrowserApiBaseUrl } from "@/lib/api";
import { formatDateTime } from "@/lib/format/date-time";

export const metadata: Metadata = {
  title: "Approval Detail · Alphora",
};

export const dynamic = "force-dynamic";

const statusToKind: Record<ApprovalStatus, StatusPillStatus> = {
  pending: "pending",
  approved: "succeeded",
  rejected: "failed",
  expired: "cancelled",
};

const dlTermClasses = "text-fg-muted text-sm";
const dlValueClasses = "text-fg text-sm font-mono";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function ApprovalDetailPage(
  props: PageProps,
): Promise<ReactElement> {
  const { id } = await props.params;

  let approval: Awaited<ReturnType<typeof getApproval>>;
  try {
    approval = await getApproval(id);
  } catch {
    notFound();
  }

  const browserApiBase = getBrowserApiBaseUrl();
  const canAct = approval.status === "pending";

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <header className="pb-6 flex items-start gap-4">
        <div className="space-y-1">
          <CapsLabel as="h1">
            {approval.ticker} · {approval.side.toUpperCase()} {approval.qty}
          </CapsLabel>
          <p className="text-sm text-fg-muted">
            mode={approval.mode} · strategy={approval.strategy_key}
          </p>
        </div>
        <StatusPill
          status={statusToKind[approval.status]}
          label={approval.status}
        />
      </header>

      <div className="grid gap-4 md:grid-cols-2 mb-6">
        <div className="rounded-md border border-line bg-surface p-4 space-y-3">
          <CapsLabel as="h2">ORDER REQUEST</CapsLabel>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
            <dt className={dlTermClasses}>Side</dt>
            <dd className={dlValueClasses}>{approval.side.toUpperCase()}</dd>

            <dt className={dlTermClasses}>Qty</dt>
            <dd className={dlValueClasses}>{approval.qty}</dd>

            <dt className={dlTermClasses}>Est. fill</dt>
            <dd className={dlValueClasses}>${approval.estimated_fill_price}</dd>

            <dt className={dlTermClasses}>Expires at</dt>
            <dd className={dlValueClasses}>
              {approval.expires_at !== null
                ? formatDateTime(approval.expires_at)
                : "—"}
            </dd>

            <dt className={dlTermClasses}>Decided by</dt>
            <dd className={dlValueClasses}>{approval.decided_by ?? "—"}</dd>

            <dt className={dlTermClasses}>Decided at</dt>
            <dd className={dlValueClasses}>
              {approval.decided_at !== null
                ? formatDateTime(approval.decided_at)
                : "—"}
            </dd>

            <dt className={dlTermClasses}>Reject reason</dt>
            <dd className={dlValueClasses}>{approval.reject_reason ?? "—"}</dd>

            <dt className={dlTermClasses}>Created</dt>
            <dd className={dlValueClasses}>
              {formatDateTime(approval.created_at)}
            </dd>
          </dl>
        </div>

        <div className="rounded-md border border-line bg-surface p-4 space-y-3">
          <CapsLabel as="h2">JUDGE VERDICT</CapsLabel>
          {approval.judge_verdict !== null ? (
            <div className="space-y-3">
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
                <dt className={dlTermClasses}>Decision</dt>
                <dd className={dlValueClasses}>
                  {approval.judge_verdict.decision}
                  {approval.judge_verdict.size_multiplier !== null
                    ? ` (× ${approval.judge_verdict.size_multiplier})`
                    : null}
                </dd>

                <dt className={dlTermClasses}>Model</dt>
                <dd className={dlValueClasses}>
                  {approval.judge_verdict.llm_model ?? "—"}
                </dd>

                <dt className={dlTermClasses}>Prompt ver.</dt>
                <dd className={dlValueClasses}>
                  {approval.judge_verdict.prompt_version ?? "—"}
                </dd>

                <dt className={dlTermClasses}>Bar ts</dt>
                <dd className={dlValueClasses}>
                  {formatDateTime(approval.judge_verdict.bar_ts)}
                </dd>
              </dl>

              <div>
                <CapsLabel className="block mb-1">REASONING</CapsLabel>
                <p className="text-sm text-fg whitespace-pre-wrap">
                  {approval.judge_verdict.reasoning_md}
                </p>
              </div>

              <details>
                <summary className="cursor-pointer text-xs uppercase tracking-[0.14em] text-fg-muted select-none">
                  Context payload
                </summary>
                <pre className="mt-2 overflow-auto rounded-md border border-line bg-surface-2 p-3 text-xs text-fg font-mono">
                  {JSON.stringify(
                    approval.judge_verdict.context_payload,
                    null,
                    2,
                  )}
                </pre>
              </details>
            </div>
          ) : (
            <p className="text-sm text-fg-subtle">No linked verdict.</p>
          )}
        </div>
      </div>

      {canAct ? (
        <ApprovalActions approvalId={approval.id} apiBase={browserApiBase} />
      ) : (
        <div className="rounded-md border border-line bg-surface-2 px-4 py-3 text-sm text-fg-muted">
          {approval.mode === "paper" && approval.status === "approved"
            ? "Auto-approved (paper mode)."
            : `Approval already ${approval.status}.`}
        </div>
      )}
    </div>
  );
}
