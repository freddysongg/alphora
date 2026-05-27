export type FunnelStageName =
  | "ingest"
  | "digest"
  | "synthesize"
  | "verify"
  | "sector_fanout"
  | "company_fanout"
  | "portfolio_brief"
  | "belief_update"
  | "consolidate";

export interface FunnelStage {
  index: number;
  name: FunnelStageName;
  label: string;
}

export const FUNNEL_STAGES: readonly FunnelStage[] = [
  { index: 1, name: "ingest", label: "ingest" },
  { index: 2, name: "digest", label: "digest" },
  { index: 3, name: "synthesize", label: "synthesize" },
  { index: 4, name: "verify", label: "verify" },
  { index: 5, name: "sector_fanout", label: "sector_fanout" },
  { index: 6, name: "company_fanout", label: "company_fanout" },
  { index: 7, name: "portfolio_brief", label: "portfolio_brief" },
  { index: 8, name: "belief_update", label: "belief_update" },
  { index: 9, name: "consolidate", label: "consolidate" },
];

export const FUNNEL_TOTAL_STAGES = FUNNEL_STAGES.length;

export function getFunnelStageByIndex(index: number): FunnelStage | null {
  if (index < 1 || index > FUNNEL_STAGES.length) {
    return null;
  }
  return FUNNEL_STAGES[index - 1] ?? null;
}
