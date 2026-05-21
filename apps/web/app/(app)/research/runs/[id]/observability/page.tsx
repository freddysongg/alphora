import type { Metadata } from "next";
import type { ReactElement } from "react";
import type { Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, CaretRight } from "@phosphor-icons/react/dist/ssr";

import { Button, CapsLabel, HexPill, StatusDot } from "@/components/ui";
import type { StatusKind } from "@/components/ui";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { cn } from "@/lib/cn";

export const metadata: Metadata = {
  title: "Run Observability · Alphora",
};

export const dynamic = "force-dynamic";

type ResearchRunDetail = components["schemas"]["ResearchRunDetail"];
type LlmCallLogPublic = components["schemas"]["LlmCallLogPublic"];
type RunCostLedger = components["schemas"]["RunCostLedger"];
type RunEvidenceFlow = components["schemas"]["RunEvidenceFlow"];
type RunGraph = components["schemas"]["RunGraph"];
type CounterfactualRunSummary =
  components["schemas"]["CounterfactualRunSummary"];
type LeakageRunPublic = components["schemas"]["LeakageRunPublic"];
type MacroBriefPublic = components["schemas"]["MacroBriefPublic"];

interface ObservabilityPageProps {
  params: Promise<{ id: string }>;
}

interface DimensionEntry {
  key: string;
  label: string;
  status: StatusKind;
  summary: string;
  href: Route;
}

const NOT_FOUND_STATUS = 404;
const LLM_CALL_FETCH_LIMIT = 500;
const LEAKAGE_FETCH_LIMIT = 50;

async function loadRunDetail(runId: string): Promise<ResearchRunDetail | null> {
  try {
    const { data } = await getServerApi().GET("/api/research-runs/{run_id}", {
      params: { path: { run_id: runId } },
      cache: "no-store",
    });
    return data ?? null;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

async function loadLlmCalls(
  runId: string,
): Promise<readonly LlmCallLogPublic[]> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research-runs/{run_id}/llm-calls",
      {
        params: {
          path: { run_id: runId },
          query: { limit: LLM_CALL_FETCH_LIMIT, offset: 0 },
        },
        cache: "no-store",
      },
    );
    return data ?? [];
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return [];
    }
    throw caught;
  }
}

async function loadCostLedger(runId: string): Promise<RunCostLedger | null> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research-runs/{run_id}/cost-ledger",
      {
        params: { path: { run_id: runId } },
        cache: "no-store",
      },
    );
    return data ?? null;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

async function loadEvidenceFlow(
  runId: string,
): Promise<RunEvidenceFlow | null> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research-runs/{run_id}/evidence-flow",
      {
        params: { path: { run_id: runId } },
        cache: "no-store",
      },
    );
    return data ?? null;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

async function loadRunGraph(runId: string): Promise<RunGraph | null> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research-runs/{run_id}/graph",
      {
        params: { path: { run_id: runId } },
        cache: "no-store",
      },
    );
    return data ?? null;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

async function loadCounterfactuals(
  runId: string,
): Promise<CounterfactualRunSummary | null> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research-runs/{run_id}/counterfactuals",
      {
        params: { path: { run_id: runId } },
        cache: "no-store",
      },
    );
    return data ?? null;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

async function loadLeakageRuns(
  runId: string,
): Promise<readonly LeakageRunPublic[]> {
  try {
    const { data } = await getServerApi().GET("/api/evals/leakage/runs", {
      params: { query: { run_id: runId, limit: LEAKAGE_FETCH_LIMIT } },
      cache: "no-store",
    });
    return data ?? [];
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return [];
    }
    throw caught;
  }
}

async function loadMacroBrief(runId: string): Promise<MacroBriefPublic | null> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research-runs/{run_id}/macro-brief",
      {
        params: { path: { run_id: runId } },
        cache: "no-store",
      },
    );
    return data ?? null;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

function formatUsd(value: string | number): string {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) {
    return "$—";
  }
  return `$${parsed.toFixed(4)}`;
}

function statusFromCount(count: number): StatusKind {
  return count > 0 ? "succeeded" : "pending";
}

function summarizeCount(count: number, noun: string): string {
  if (count === 0) {
    return "No data";
  }
  return `${count} ${noun}`;
}

function deriveDimensions(args: {
  runId: string;
  calls: readonly LlmCallLogPublic[];
  costLedger: RunCostLedger | null;
  evidenceFlow: RunEvidenceFlow | null;
  runGraph: RunGraph | null;
  counterfactuals: CounterfactualRunSummary | null;
  leakage: readonly LeakageRunPublic[];
  macroBrief: MacroBriefPublic | null;
}): readonly DimensionEntry[] {
  const {
    runId,
    calls,
    costLedger,
    evidenceFlow,
    runGraph,
    counterfactuals,
    leakage,
    macroBrief,
  } = args;
  const base = `/research/runs/${runId}/observability`;
  const callCount = calls.length;
  const evidenceSources = evidenceFlow?.sources.length ?? 0;
  const evidenceCount = evidenceFlow?.total_evidence ?? evidenceSources;
  const graphNodes = runGraph?.nodes.length ?? 0;
  const cfCount = counterfactuals?.perturbations.length ?? 0;
  const leakageCount = leakage.length;
  const claimCount = macroBrief?.brief.cited_claims.length ?? 0;
  const totalCost = costLedger?.total_cost_usd ?? null;
  return [
    {
      key: "llm-calls",
      label: "LLM CALLS",
      status: statusFromCount(callCount),
      summary: summarizeCount(callCount, "calls"),
      href: `${base}/llm-calls` as Route,
    },
    {
      key: "cost",
      label: "COST LEDGER",
      status: totalCost !== null ? "succeeded" : "pending",
      summary: totalCost !== null ? formatUsd(totalCost) : "No cost recorded",
      href: `${base}/cost` as Route,
    },
    {
      key: "evidence",
      label: "EVIDENCE FLOW",
      status: statusFromCount(evidenceCount),
      summary:
        evidenceCount === 0
          ? "No data"
          : `${evidenceCount} evidence · ${evidenceSources} sources`,
      href: `${base}/evidence` as Route,
    },
    {
      key: "graph",
      label: "KNOWLEDGE GRAPH",
      status: statusFromCount(graphNodes),
      summary: summarizeCount(graphNodes, "nodes"),
      href: `${base}/graph` as Route,
    },
    {
      key: "counterfactuals",
      label: "COUNTERFACTUALS",
      status: statusFromCount(cfCount),
      summary: summarizeCount(cfCount, "perturbations"),
      href: `${base}/counterfactuals` as Route,
    },
    {
      key: "leakage",
      label: "LEAKAGE",
      status: statusFromCount(leakageCount),
      summary: summarizeCount(leakageCount, "holdout runs"),
      href: `${base}/leakage` as Route,
    },
    {
      key: "claims",
      label: "CLAIM REVIEW",
      status: statusFromCount(claimCount),
      summary: summarizeCount(claimCount, "cited claims"),
      href: `${base}/claims` as Route,
    },
  ];
}

export default async function RunObservabilityPage(
  props: ObservabilityPageProps,
): Promise<ReactElement> {
  const { id } = await props.params;
  const detail = await loadRunDetail(id);
  if (detail === null) {
    notFound();
  }
  const isFunnel = detail.strategy === "funnel_research";
  const [
    calls,
    costLedger,
    evidenceFlow,
    runGraph,
    counterfactuals,
    leakage,
    macroBrief,
  ] = await Promise.all([
    loadLlmCalls(id),
    loadCostLedger(id),
    loadEvidenceFlow(id),
    loadRunGraph(id),
    loadCounterfactuals(id),
    loadLeakageRuns(id),
    isFunnel ? loadMacroBrief(id) : Promise.resolve(null),
  ]);
  const dimensions = deriveDimensions({
    runId: id,
    calls,
    costLedger,
    evidenceFlow,
    runGraph,
    counterfactuals,
    leakage,
    macroBrief,
  });
  const runHref = `/research/runs/${id}` as Route;
  return (
    <div className="max-w-[1100px] mx-auto" data-testid="observability-page">
      <header className="sticky top-0 z-10 bg-canvas border-b border-line">
        <div className="flex items-center gap-4 px-6 py-4">
          <Button asChild size="sm" variant="ghost" aria-label="Back to run">
            <Link href={runHref}>
              <ArrowLeft size={12} weight="regular" />
            </Link>
          </Button>
          <span className="text-2xl font-mono tabular-nums text-fg">
            OBSERVABILITY
          </span>
          <HexPill value={detail.id} />
        </div>
      </header>

      <div className="px-6 pt-6 pb-12">
        <ul className="flex flex-col">
          {dimensions.map((entry) => (
            <DimensionRow key={entry.key} entry={entry} />
          ))}
        </ul>
      </div>
    </div>
  );
}

interface DimensionRowProps {
  entry: DimensionEntry;
}

function DimensionRow(props: DimensionRowProps): ReactElement {
  const { entry } = props;
  return (
    <li>
      <Link
        href={entry.href}
        className={cn(
          "group block px-3 -mx-3 rounded-md transition-colors duration-150",
          "hover:bg-surface-2",
        )}
      >
        <div className="flex items-center gap-4 py-4 border-t border-line/60">
          <div className="w-56 shrink-0">
            <CapsLabel className="text-fg">{entry.label}</CapsLabel>
          </div>
          <StatusDot status={entry.status} />
          <span className="text-sm text-fg-muted truncate min-w-0 flex-1">
            {entry.summary}
          </span>
          <CaretRight
            size={14}
            weight="regular"
            className="text-fg-subtle group-hover:text-fg shrink-0"
          />
        </div>
      </Link>
    </li>
  );
}
