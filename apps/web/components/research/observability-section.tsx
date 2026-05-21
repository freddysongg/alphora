"use client";

import { useState } from "react";
import type { ReactElement, ReactNode } from "react";

import {
  CapsLabel,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui";
import type { StatusPillStatus } from "@/components/ui";
import { cn } from "@/lib/cn";
import { CostLedger } from "@/components/research/cost-ledger";
import type { SourceClientCacheStats } from "@/components/research/cost-ledger";
import { CounterfactualMatrix } from "@/components/research/counterfactual-matrix";
import { EvidenceFlow } from "@/components/research/evidence-flow";
import type { InlineClaim } from "@/components/research/inline-claim-review";
import { InlineClaimReviewSection } from "@/components/research/inline-claim-review-section";
import { KnowledgeGraph } from "@/components/research/knowledge-graph";
import { LeakageChart } from "@/components/research/leakage-chart";
import { RunTimelineFlame } from "@/components/research/run-timeline-flame";
import type { components } from "@/lib/api";
import { isTerminal } from "@/lib/research/status-mapping";

type LlmCallLogPublic = components["schemas"]["LlmCallLogPublic"];
type RunCostLedger = components["schemas"]["RunCostLedger"];
type RunEvidenceFlow = components["schemas"]["RunEvidenceFlow"];
type RunGraph = components["schemas"]["RunGraph"];
type CounterfactualRunSummary =
  components["schemas"]["CounterfactualRunSummary"];
type LeakageRunPublic = components["schemas"]["LeakageRunPublic"];
type RunStatus = components["schemas"]["RunStatusEnum"];

const DIMENSION_KEYS = [
  "llm-calls",
  "cost",
  "evidence",
  "graph",
  "counterfactuals",
  "leakage",
  "claims",
] as const;

type DimensionKey = (typeof DIMENSION_KEYS)[number];

export interface ObservabilitySectionProps {
  runId: string;
  runStatus: RunStatus;
  llmCalls: readonly LlmCallLogPublic[];
  costLedger: RunCostLedger | null;
  evidenceFlow: RunEvidenceFlow | null;
  runGraph: RunGraph | null;
  counterfactuals: CounterfactualRunSummary | null;
  leakage: readonly LeakageRunPublic[];
  claims: readonly InlineClaim[];
  sourceClientCacheStats: SourceClientCacheStats | null;
  defaultWeekStart: string;
}

interface DimensionMeta {
  key: DimensionKey;
  label: string;
  status: StatusPillStatus;
  summary: string;
  hasData: boolean;
  description: string;
}

const DIMENSION_DESCRIPTIONS: Record<DimensionKey, string> = {
  "llm-calls":
    "Every model call made during this run — prompt, response, tokens, latency, cost. Click into a call to debug exactly what the model said.",
  cost:
    "Dollars spent, broken down by stage (ingest, digest, synthesize, etc.) and by source-client cache hit rate. Tells you where the money went.",
  evidence:
    "Per-source counts: which providers (Polygon, Polymarket, FRED, …) returned how many documents, how many chunks were extracted, and how many got cited in the final brief.",
  graph:
    "Entities (companies, sectors, events) and relations (e.g. supplies, regulated_by) the model extracted from this run's evidence. The worldview it built before deciding.",
  counterfactuals:
    "Perturbations of the inputs — 'what if Apple beat earnings by 10% instead' — to test how robust the conclusions are. Quantifies confidence.",
  leakage:
    "Look-ahead bias detection. Holdout tests check whether the run relied on evidence dated AFTER the trade date, which would invalidate the thesis.",
  claims:
    "Atomic claims the brief made, each linked back to the source chunk it came from. Score each claim and the reviewer leaves a trail for next time.",
};

function statusFromCount(
  count: number,
  runStatus: RunStatus,
): StatusPillStatus {
  if (count > 0) {
    return "succeeded";
  }
  if (runStatus === "running") {
    return "running";
  }
  if (runStatus === "failed") {
    return "failed";
  }
  if (runStatus === "cancelled") {
    return "cancelled";
  }
  return "pending";
}

function summarize(count: number, noun: string, runStatus: RunStatus): string {
  if (count > 0) {
    return `${count.toLocaleString()} ${noun}`;
  }
  if (runStatus === "running") {
    return "Streaming…";
  }
  if (runStatus === "failed") {
    return "Run failed";
  }
  if (runStatus === "cancelled") {
    return "Cancelled";
  }
  if (runStatus === "queued") {
    return "Queued";
  }
  return "No data";
}

function formatUsd(value: string | number): string {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) {
    return "$—";
  }
  return `$${parsed.toFixed(4)}`;
}

function deriveDimensions(args: {
  runStatus: RunStatus;
  llmCalls: readonly LlmCallLogPublic[];
  costLedger: RunCostLedger | null;
  evidenceFlow: RunEvidenceFlow | null;
  runGraph: RunGraph | null;
  counterfactuals: CounterfactualRunSummary | null;
  leakage: readonly LeakageRunPublic[];
  claims: readonly InlineClaim[];
}): readonly DimensionMeta[] {
  const {
    runStatus,
    llmCalls,
    costLedger,
    evidenceFlow,
    runGraph,
    counterfactuals,
    leakage,
    claims,
  } = args;
  const evidenceCount =
    evidenceFlow?.total_evidence ?? evidenceFlow?.sources.length ?? 0;
  const graphNodes = runGraph?.nodes.length ?? 0;
  const cfCount = counterfactuals?.perturbations.length ?? 0;
  const totalCost = costLedger?.total_cost_usd ?? null;
  return [
    {
      key: "llm-calls",
      label: "LLM CALLS",
      status: statusFromCount(llmCalls.length, runStatus),
      summary: summarize(llmCalls.length, "calls", runStatus),
      hasData: llmCalls.length > 0,
      description: DIMENSION_DESCRIPTIONS["llm-calls"],
    },
    {
      key: "cost",
      label: "COST LEDGER",
      status: totalCost !== null ? "succeeded" : statusFromCount(0, runStatus),
      summary:
        totalCost !== null ? formatUsd(totalCost) : summarize(0, "", runStatus),
      hasData: costLedger !== null && costLedger.stages.length > 0,
      description: DIMENSION_DESCRIPTIONS.cost,
    },
    {
      key: "evidence",
      label: "EVIDENCE FLOW",
      status: statusFromCount(evidenceCount, runStatus),
      summary: summarize(evidenceCount, "evidence", runStatus),
      hasData: evidenceFlow !== null && evidenceFlow.sources.length > 0,
      description: DIMENSION_DESCRIPTIONS.evidence,
    },
    {
      key: "graph",
      label: "KNOWLEDGE GRAPH",
      status: statusFromCount(graphNodes, runStatus),
      summary: summarize(graphNodes, "nodes", runStatus),
      hasData: runGraph !== null && runGraph.nodes.length > 0,
      description: DIMENSION_DESCRIPTIONS.graph,
    },
    {
      key: "counterfactuals",
      label: "COUNTERFACTUALS",
      status: statusFromCount(cfCount, runStatus),
      summary: summarize(cfCount, "perturbations", runStatus),
      hasData:
        counterfactuals !== null && counterfactuals.perturbations.length > 0,
      description: DIMENSION_DESCRIPTIONS.counterfactuals,
    },
    {
      key: "leakage",
      label: "LEAKAGE",
      status: statusFromCount(leakage.length, runStatus),
      summary: summarize(leakage.length, "holdouts", runStatus),
      hasData: leakage.length > 0,
      description: DIMENSION_DESCRIPTIONS.leakage,
    },
    {
      key: "claims",
      label: "CLAIM REVIEW",
      status: statusFromCount(claims.length, runStatus),
      summary: summarize(claims.length, "cited claims", runStatus),
      hasData: claims.length > 0,
      description: DIMENSION_DESCRIPTIONS.claims,
    },
  ];
}

export function ObservabilitySection(
  props: ObservabilitySectionProps,
): ReactElement {
  const {
    runId,
    runStatus,
    llmCalls,
    costLedger,
    evidenceFlow,
    runGraph,
    counterfactuals,
    leakage,
    claims,
    sourceClientCacheStats,
    defaultWeekStart,
  } = props;
  const [activeKey, setActiveKey] = useState<DimensionKey>("llm-calls");

  const dimensions = deriveDimensions({
    runStatus,
    llmCalls,
    costLedger,
    evidenceFlow,
    runGraph,
    counterfactuals,
    leakage,
    claims,
  });
  const active = dimensions.find((entry) => entry.key === activeKey) ?? null;
  const activeSummary = active?.summary ?? "";

  return (
    <section
      id="observability"
      className="scroll-mt-16 border border-line rounded-xl bg-surface overflow-hidden"
      data-testid="observability-section"
      aria-label="Observability"
    >
      <div className="flex items-center justify-between border-b border-line px-4 h-10 bg-panel">
        <CapsLabel className="text-fg">OBSERVABILITY</CapsLabel>
        <span className="text-[11px] font-mono text-fg-subtle">
          {activeSummary}
        </span>
      </div>
      <Tabs
        value={activeKey}
        onValueChange={(value) => setActiveKey(value as DimensionKey)}
      >
        <TooltipProvider delayDuration={250}>
          <TabsList className="px-4 flex-wrap gap-x-1 gap-y-0 border-b">
            {dimensions.map((entry) => (
              <Tooltip key={entry.key}>
                <TooltipTrigger asChild>
                  <TabsTrigger
                    value={entry.key}
                    className="data-[state=active]:text-accent-text"
                  >
                    <span className="inline-flex items-center gap-2">
                      <StatusIndicator status={entry.status} />
                      <span>{entry.label}</span>
                    </span>
                  </TabsTrigger>
                </TooltipTrigger>
                <TooltipContent
                  side="bottom"
                  align="start"
                  className="max-w-[320px] whitespace-normal text-[12px] font-sans leading-snug text-fg-muted normal-case tracking-normal px-3 py-2"
                >
                  {entry.description}
                </TooltipContent>
              </Tooltip>
            ))}
          </TabsList>
        </TooltipProvider>

        <div className="p-4 max-h-[640px] overflow-y-auto">
          <TabsContent value="llm-calls" className="pt-0">
            <DimensionShell
              hasData={llmCalls.length > 0}
              runStatus={runStatus}
              emptyLabel="LLM calls"
            >
              <RunTimelineFlame calls={llmCalls} />
            </DimensionShell>
          </TabsContent>
          <TabsContent value="cost" className="pt-0">
            <DimensionShell
              hasData={costLedger !== null && costLedger.stages.length > 0}
              runStatus={runStatus}
              emptyLabel="cost data"
            >
              <CostLedger
                ledger={costLedger}
                sourceClientCacheStats={sourceClientCacheStats}
              />
            </DimensionShell>
          </TabsContent>
          <TabsContent value="evidence" className="pt-0">
            <DimensionShell
              hasData={evidenceFlow !== null && evidenceFlow.sources.length > 0}
              runStatus={runStatus}
              emptyLabel="evidence"
            >
              <EvidenceFlow flow={evidenceFlow} />
            </DimensionShell>
          </TabsContent>
          <TabsContent value="graph" className="pt-0">
            <DimensionShell
              hasData={runGraph !== null && runGraph.nodes.length > 0}
              runStatus={runStatus}
              emptyLabel="graph nodes"
            >
              <KnowledgeGraph graph={runGraph} />
            </DimensionShell>
          </TabsContent>
          <TabsContent value="counterfactuals" className="pt-0">
            <DimensionShell
              hasData={
                counterfactuals !== null &&
                counterfactuals.perturbations.length > 0
              }
              runStatus={runStatus}
              emptyLabel="counterfactual perturbations"
            >
              <CounterfactualMatrix
                perturbations={counterfactuals?.perturbations ?? []}
              />
            </DimensionShell>
          </TabsContent>
          <TabsContent value="leakage" className="pt-0">
            <DimensionShell
              hasData={leakage.length > 0}
              runStatus={runStatus}
              emptyLabel="leakage holdouts"
            >
              <LeakageChart runs={leakage} />
            </DimensionShell>
          </TabsContent>
          <TabsContent value="claims" className="pt-0">
            <DimensionShell
              hasData={claims.length > 0}
              runStatus={runStatus}
              emptyLabel="cited claims"
            >
              <InlineClaimReviewSection
                runId={runId}
                defaultWeekStart={defaultWeekStart}
                claims={claims}
              />
            </DimensionShell>
          </TabsContent>
        </div>
      </Tabs>
    </section>
  );
}

interface DimensionShellProps {
  hasData: boolean;
  runStatus: RunStatus;
  emptyLabel: string;
  children: ReactNode;
}

function DimensionShell(props: DimensionShellProps): ReactElement {
  const { hasData, runStatus, emptyLabel, children } = props;
  if (hasData) {
    return <>{children}</>;
  }
  if (!isTerminal(runStatus)) {
    return <DimensionSkeleton />;
  }
  return (
    <p className="text-sm text-fg-subtle py-6">
      No {emptyLabel} captured for this run.
    </p>
  );
}

function DimensionSkeleton(): ReactElement {
  return (
    <div className="flex flex-col gap-3" data-testid="observability-skeleton">
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-32 w-full" />
      <div className="grid grid-cols-3 gap-3">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
      <Skeleton className="h-24 w-full" />
    </div>
  );
}

const dotClasses: Record<StatusPillStatus, string> = {
  pending: "border border-fg-muted bg-transparent",
  running: "bg-[var(--color-status-running)]",
  succeeded: "bg-[var(--color-status-success)]",
  failed: "bg-[var(--color-status-failed)]",
  cancelled: "bg-[var(--color-status-cancelled)]",
  paused: "bg-[var(--color-status-paused)]",
};

function StatusIndicator(props: { status: StatusPillStatus }): ReactElement {
  const { status } = props;
  const isRunning = status === "running";
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-block h-1.5 w-1.5 rounded-full",
        dotClasses[status],
        isRunning && "pulse-dot",
      )}
    />
  );
}
