"use client";

import { useCallback, useMemo, useState } from "react";
import type { ReactElement } from "react";
import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CaretRight } from "@phosphor-icons/react/dist/ssr";
import { Button, CapsLabel, HexPill, StatusDot } from "@/components/ui";
import type { StatusKind } from "@/components/ui";
import type { components } from "@/lib/api";
import { RunSseProvider } from "@/components/research/run-sse-context";
import { HumanReviewForm } from "@/components/research/human-review-form";
import { HumanReviewSummaryWidget } from "@/components/research/human-review-summary";
import type { HypothesisBeliefBundle } from "@/components/research/hypothesis-belief-explainer";
import type { HypothesisLifecycleBundle } from "@/components/research/hypothesis-lifecycle-card";
import { LiveCostStrip } from "@/components/research/live-cost-strip";
import type { CostMeterState } from "@/components/research/live-cost-strip";
import {
  isTerminal,
  runStatusToStatusKind,
} from "@/lib/research/status-mapping";
import { cn } from "@/lib/cn";
import { CancelRunButton } from "./cancel-run-button";

type ResearchRunDetail = components["schemas"]["ResearchRunDetail"];
type RunStatus = components["schemas"]["RunStatusEnum"];
type MacroBriefPublic = components["schemas"]["MacroBriefPublic"];
type PortfolioBriefPublic = components["schemas"]["PortfolioBriefPublic"];
type HumanReviewSummary = components["schemas"]["HumanReviewSummary"];
type RunCostEstimate = components["schemas"]["RunCostEstimate"];
type ScopePayload = ResearchRunDetail["scope_payload"];

const statusToLabel: Record<RunStatus, string> = {
  queued: "QUEUED",
  running: "RUNNING",
  succeeded: "SUCCEEDED",
  failed: "FAILED",
  cancelled: "CANCELLED",
  paused: "PAUSED",
};

const SCOPE_UNIVERSE_LABEL: Record<string, string> = {
  us_equities: "US EQUITIES",
};

interface StageEntry {
  key: string;
  label: string;
  count: string | null;
  status: StatusKind;
  summary: string;
  href: Route | null;
}

export interface RunDetailProps {
  detail: ResearchRunDetail;
  macroBrief: MacroBriefPublic | null;
  portfolioBrief: PortfolioBriefPublic | null;
  initialCostState: CostMeterState;
  initialSeenLogIds: readonly string[];
  costEstimate: RunCostEstimate | null;
  humanReviewSummary: HumanReviewSummary;
  defaultWeekStart: string;
  beliefBundles: readonly HypothesisBeliefBundle[];
  lifecycleBundles: readonly HypothesisLifecycleBundle[];
}

function resolveHeaderLabel(detail: ResearchRunDetail): string {
  if (detail.ticker !== null) {
    return detail.ticker;
  }
  return resolveScopeLabel(detail.scope_payload) ?? "—";
}

function resolveScopeLabel(scope: ScopePayload): string | null {
  if (scope === null || scope === undefined) {
    return null;
  }
  const record = scope as Record<string, unknown>;
  const kind = record["kind"];
  const universe = record["universe"];
  if (typeof kind !== "string" || typeof universe !== "string") {
    return null;
  }
  const universeLabel =
    SCOPE_UNIVERSE_LABEL[universe] ?? universe.toUpperCase();
  return `${kind.toUpperCase()} · ${universeLabel}`;
}

function deriveMacroStage(
  detail: ResearchRunDetail,
  macroBrief: MacroBriefPublic | null,
): StageEntry {
  const runId = detail.id;
  if (macroBrief !== null) {
    const themeCount = macroBrief.brief.themes.length;
    const sectorCallCount = macroBrief.brief.sector_calls.length;
    return {
      key: "macro",
      label: "MACRO BRIEF",
      count: null,
      status: "succeeded",
      summary: `${themeCount} themes · ${sectorCallCount} sector calls`,
      href: `/research/runs/${runId}/macro-brief` as Route,
    };
  }
  return {
    key: "macro",
    label: "MACRO BRIEF",
    count: null,
    status: stageStatusForMissing(detail.status),
    summary: missingSummary(detail.status, "Generating"),
    href: null,
  };
}

function deriveHypothesesStage(
  detail: ResearchRunDetail,
  bundles: readonly HypothesisBeliefBundle[],
  lifecycle: readonly HypothesisLifecycleBundle[],
): StageEntry {
  const runId = detail.id;
  if (bundles.length === 0) {
    return {
      key: "hypotheses",
      label: "HYPOTHESES",
      count: null,
      status: stageStatusForMissing(detail.status),
      summary: missingSummary(detail.status, "Pending macro brief"),
      href: null,
    };
  }
  const activeCount = lifecycle.filter(
    (bundle) => bundle.hypothesis.state === "active",
  ).length;
  const validatedCount = lifecycle.filter(
    (bundle) => bundle.hypothesis.state === "validated",
  ).length;
  const falsifiedCount = lifecycle.filter(
    (bundle) => bundle.hypothesis.state === "falsified",
  ).length;
  return {
    key: "hypotheses",
    label: "HYPOTHESES",
    count: `(${bundles.length})`,
    status: "succeeded",
    summary: `${activeCount} active · ${validatedCount} validated · ${falsifiedCount} falsified`,
    href: `/research/runs/${runId}/hypotheses` as Route,
  };
}

function deriveSectorsStage(
  detail: ResearchRunDetail,
  macroBrief: MacroBriefPublic | null,
): StageEntry {
  const runId = detail.id;
  const sectorBriefs = macroBrief?.sector_briefs ?? [];
  if (sectorBriefs.length === 0) {
    return {
      key: "sectors",
      label: "SECTORS",
      count: null,
      status: stageStatusForMissing(detail.status),
      summary: missingSummary(detail.status, "Awaiting fan-out"),
      href: null,
    };
  }
  const sectorNames = sectorBriefs
    .map((sb) => sb.brief.sector_name)
    .slice(0, 3)
    .join(", ");
  const overflow =
    sectorBriefs.length > 3 ? ` + ${sectorBriefs.length - 3} more` : "";
  return {
    key: "sectors",
    label: "SECTORS",
    count: `(${sectorBriefs.length})`,
    status: "succeeded",
    summary: `${sectorNames}${overflow}`,
    href: `/research/runs/${runId}/sectors` as Route,
  };
}

function deriveCompaniesStage(
  detail: ResearchRunDetail,
  macroBrief: MacroBriefPublic | null,
): StageEntry {
  const runId = detail.id;
  const sectorBriefs = macroBrief?.sector_briefs ?? [];
  const totalCompanies = sectorBriefs.reduce(
    (sum, sb) => sum + sb.brief.companies.length,
    0,
  );
  if (totalCompanies === 0) {
    return {
      key: "companies",
      label: "COMPANIES",
      count: null,
      status: stageStatusForMissing(detail.status),
      summary: missingSummary(detail.status, "Awaiting sector briefs"),
      href: null,
    };
  }
  return {
    key: "companies",
    label: "COMPANIES",
    count: `(${totalCompanies})`,
    status: "succeeded",
    summary: `Across ${sectorBriefs.length} sectors`,
    href: `/research/runs/${runId}/companies` as Route,
  };
}

function derivePortfolioStage(
  detail: ResearchRunDetail,
  portfolioBrief: PortfolioBriefPublic | null,
): StageEntry {
  const runId = detail.id;
  if (portfolioBrief !== null) {
    const pickCount = portfolioBrief.brief.companies.length;
    return {
      key: "portfolio",
      label: "PORTFOLIO BRIEF",
      count: null,
      status: "succeeded",
      summary: `${pickCount} picks`,
      href: `/research/runs/${runId}/portfolio-brief` as Route,
    };
  }
  return {
    key: "portfolio",
    label: "PORTFOLIO BRIEF",
    count: null,
    status: stageStatusForMissing(detail.status),
    summary: missingSummary(detail.status, "Awaiting company theses"),
    href: null,
  };
}

function deriveHumanReviewStage(
  detail: ResearchRunDetail,
  summary: HumanReviewSummary,
): StageEntry {
  const submittedWeeks = summary.weeks.length;
  if (!isTerminal(detail.status)) {
    return {
      key: "human-review",
      label: "HUMAN REVIEW",
      count: null,
      status: "pending",
      summary: "Available after run completes",
      href: null,
    };
  }
  if (submittedWeeks > 0) {
    return {
      key: "human-review",
      label: "HUMAN REVIEW",
      count: null,
      status: "succeeded",
      summary: `${submittedWeeks} submitted reviews`,
      href: null,
    };
  }
  return {
    key: "human-review",
    label: "HUMAN REVIEW",
    count: null,
    status: "pending",
    summary: "Open form below",
    href: null,
  };
}

function stageStatusForMissing(runStatus: RunStatus): StatusKind {
  if (runStatus === "failed" || runStatus === "cancelled") {
    return "stale";
  }
  if (runStatus === "running") {
    return "live";
  }
  return "pending";
}

function missingSummary(runStatus: RunStatus, generating: string): string {
  if (runStatus === "failed") {
    return "Did not run";
  }
  if (runStatus === "cancelled") {
    return "Cancelled";
  }
  if (runStatus === "running") {
    return generating;
  }
  return "—";
}

export function RunDetail(props: RunDetailProps): ReactElement {
  const {
    detail,
    macroBrief,
    portfolioBrief,
    initialCostState,
    initialSeenLogIds,
    costEstimate,
    humanReviewSummary,
    defaultWeekStart,
    beliefBundles,
    lifecycleBundles,
  } = props;
  const router = useRouter();
  const [optimisticStatus, setOptimisticStatus] = useState<RunStatus | null>(
    null,
  );
  const resolvedStatus = optimisticStatus ?? detail.status;
  const isCancellable =
    resolvedStatus === "queued" ||
    resolvedStatus === "running" ||
    resolvedStatus === "paused";
  const isLogStreamTerminal = isTerminal(resolvedStatus);
  const headerLabel = resolveHeaderLabel(detail);

  const stages = useMemo<readonly StageEntry[]>(
    () => [
      deriveMacroStage(detail, macroBrief),
      deriveHypothesesStage(detail, beliefBundles, lifecycleBundles),
      deriveSectorsStage(detail, macroBrief),
      deriveCompaniesStage(detail, macroBrief),
      derivePortfolioStage(detail, portfolioBrief),
      deriveHumanReviewStage(detail, humanReviewSummary),
    ],
    [
      detail,
      macroBrief,
      portfolioBrief,
      beliefBundles,
      lifecycleBundles,
      humanReviewSummary,
    ],
  );

  const handleOptimisticCancel = useCallback((): void => {
    setOptimisticStatus("cancelled");
  }, []);
  const handleCancelRollback = useCallback((): void => {
    setOptimisticStatus(null);
  }, []);
  const handleReviewSubmitted = useCallback((): void => {
    router.refresh();
  }, [router]);

  const showReviewForm =
    isTerminal(resolvedStatus) && humanReviewSummary.weeks.length === 0;

  return (
    <RunSseProvider runId={detail.id} isTerminal={isLogStreamTerminal}>
      <div className="max-w-[1100px] mx-auto">
        <header className="sticky top-0 z-10 bg-canvas border-b border-line">
          <div className="flex items-center gap-4 px-6 py-4">
            <span className="text-2xl font-mono tabular-nums text-fg">
              {headerLabel}
            </span>
            <HexPill value={detail.id} />
            <StatusDot
              status={runStatusToStatusKind(resolvedStatus)}
              label={statusToLabel[resolvedStatus]}
            />
            <div className="flex-1" />
            {isCancellable ? (
              <CancelRunButton
                runId={detail.id}
                onOptimisticCancel={handleOptimisticCancel}
                onCancelRollback={handleCancelRollback}
              />
            ) : null}
          </div>
        </header>

        <div className="px-6 pt-6 pb-12 flex flex-col gap-8">
          {detail.error_message !== null ? (
            <div
              role="alert"
              className="rounded-md border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
            >
              <span className="font-medium">Run halted:</span>{" "}
              {detail.error_message}
            </div>
          ) : null}

          <ul className="flex flex-col">
            {stages.map((entry) => (
              <StageRow key={entry.key} entry={entry} />
            ))}
          </ul>

          {showReviewForm ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <HumanReviewForm
                runId={detail.id}
                defaultWeekStart={defaultWeekStart}
                onSubmitted={handleReviewSubmitted}
              />
              <HumanReviewSummaryWidget summary={humanReviewSummary} />
            </div>
          ) : humanReviewSummary.weeks.length > 0 ? (
            <HumanReviewSummaryWidget summary={humanReviewSummary} />
          ) : null}

          <LiveCostStrip
            runId={detail.id}
            initialState={initialCostState}
            initialSeenLogIds={initialSeenLogIds}
            costEstimate={costEstimate}
          />
        </div>
      </div>
    </RunSseProvider>
  );
}

interface StageRowProps {
  entry: StageEntry;
}

function StageRow(props: StageRowProps): ReactElement {
  const { entry } = props;
  const inner = (
    <div className="flex items-center gap-4 py-4 border-t border-line/60">
      <div className="flex items-center gap-2 w-56 shrink-0">
        <CapsLabel className="text-fg">{entry.label}</CapsLabel>
        {entry.count !== null ? (
          <span className="font-mono text-xs text-fg-subtle">
            {entry.count}
          </span>
        ) : null}
      </div>
      <StatusDot status={entry.status} />
      <span className="text-sm text-fg-muted truncate min-w-0 flex-1">
        {entry.summary}
      </span>
      {entry.href !== null ? (
        <CaretRight
          size={14}
          weight="regular"
          className="text-fg-subtle group-hover:text-fg shrink-0"
        />
      ) : null}
    </div>
  );
  if (entry.href === null) {
    return <li>{inner}</li>;
  }
  return (
    <li>
      <Link
        href={entry.href}
        className={cn(
          "group block px-3 -mx-3 rounded-md transition-colors duration-150",
          "hover:bg-surface-2",
        )}
      >
        {inner}
      </Link>
    </li>
  );
}
