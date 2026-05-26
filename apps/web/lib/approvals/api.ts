import { z } from "zod";

import { getApiBaseUrl } from "@/lib/api";

const ApprovalSchema = z.object({
  id: z.string().uuid(),
  run_id: z.string().uuid(),
  judge_verdict_id: z.string().uuid().nullable(),
  strategy_key: z.string(),
  ticker: z.string(),
  side: z.enum(["buy", "sell"]),
  qty: z.string(),
  estimated_fill_price: z.string(),
  mode: z.enum(["paper", "live"]),
  status: z.enum(["pending", "approved", "rejected", "expired"]),
  decided_by: z.string().nullable(),
  decided_at: z.string().nullable(),
  reject_reason: z.string().nullable(),
  expires_at: z.string().nullable(),
  created_at: z.string(),
});

const JudgeVerdictSummarySchema = z.object({
  id: z.string().uuid(),
  decision: z.string(),
  size_multiplier: z.number().nullable(),
  reasoning_md: z.string(),
  context_payload: z.record(z.string(), z.unknown()),
  llm_model: z.string().nullable(),
  prompt_version: z.string().nullable(),
  bar_ts: z.string(),
});

const ApprovalDetailSchema = ApprovalSchema.extend({
  judge_verdict: JudgeVerdictSummarySchema.nullable(),
});

export type Approval = z.infer<typeof ApprovalSchema>;
export type ApprovalDetail = z.infer<typeof ApprovalDetailSchema>;
export type JudgeVerdictSummary = z.infer<typeof JudgeVerdictSummarySchema>;

export type ApprovalStatus = Approval["status"];
export type ApprovalMode = Approval["mode"];

interface ListParams {
  status?: ApprovalStatus;
  mode?: ApprovalMode;
}

export async function listApprovals(
  params: ListParams = {},
): Promise<Approval[]> {
  const search = new URLSearchParams();
  if (params.status !== undefined) search.set("status", params.status);
  if (params.mode !== undefined) search.set("mode", params.mode);
  const qs = search.toString();
  const url = `${getApiBaseUrl()}/api/approvals${qs ? `?${qs}` : ""}`;
  const resp = await fetch(url, { cache: "no-store" });
  if (!resp.ok) {
    throw new Error(`listApprovals failed: ${resp.status}`);
  }
  const data: unknown = await resp.json();
  return z.array(ApprovalSchema).parse(data);
}

export async function getApproval(id: string): Promise<ApprovalDetail> {
  const url = `${getApiBaseUrl()}/api/approvals/${id}`;
  const resp = await fetch(url, { cache: "no-store" });
  if (resp.status === 404) {
    throw new Error("approval not found");
  }
  if (!resp.ok) {
    throw new Error(`getApproval failed: ${resp.status}`);
  }
  const data: unknown = await resp.json();
  return ApprovalDetailSchema.parse(data);
}
