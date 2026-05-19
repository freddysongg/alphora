"use client";

import { useMemo, useState } from "react";
import type { ReactElement } from "react";
import type { Route } from "next";
import Link from "next/link";
import type { ColumnDef } from "@tanstack/react-table";
import {
  Button,
  CapsLabel,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  DataTable,
  HexPill,
  MetricQuadrant,
  StatusDot,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui";
import type { MetricTile, StatusKind } from "@/components/ui";
import type { components } from "@/lib/api";
import { readNumber, readStringArray } from "@/lib/api/config";
import { formatWallClock } from "@/lib/format/wall-clock";
import { mapEventsToLogLines } from "@/lib/research/map-events-to-log-lines";
import {
  compareAnalysts,
  resolveAnalystLabel,
} from "@/lib/research/analyst-labels";
import {
  isTerminal,
  provenanceStatusToStatusKind,
  runStatusToStatusKind,
} from "@/lib/research/status-mapping";
import { RunLogStream } from "@/components/research/run-log-stream";
import { cn } from "@/lib/cn";
import { CancelRunButton } from "./cancel-run-button";
import { MacroBriefDetail } from "./macro-brief-detail";
import { RerunButton } from "./rerun-button";

type ResearchRunDetail = components["schemas"]["ResearchRunDetail"];
type RunStatus = components["schemas"]["RunStatusEnum"];
type FinalRating = components["schemas"]["FinalRatingEnum"];
type RunReport = components["schemas"]["RunReportPublic"];
type SourceProvenance = components["schemas"]["SourceProvenancePublic"];
type MacroBriefPublic = components["schemas"]["MacroBriefPublic"];

type TabKey =
  | "overview"
  | "reports"
  | "debate"
  | "risk"
  | "logs"
  | "provenance";

interface TabConfig {
  key: TabKey;
  label: string;
}

const tabConfigs: readonly TabConfig[] = [
  { key: "overview", label: "OVERVIEW" },
  { key: "reports", label: "REPORTS" },
  { key: "debate", label: "DEBATE" },
  { key: "risk", label: "RISK" },
  { key: "logs", label: "LOGS" },
  { key: "provenance", label: "PROVENANCE" },
];

const statusToLabel: Record<RunStatus, string> = {
  queued: "QUEUED",
  running: "RUNNING",
  succeeded: "SUCCEEDED",
  failed: "FAILED",
  cancelled: "CANCELLED",
  paused: "PAUSED",
};

const ratingToLabel: Record<FinalRating, string> = {
  buy: "BUY",
  hold: "HOLD",
  sell: "SELL",
  none: "—",
};

const ratingToAccent: Record<FinalRating, string> = {
  buy: "text-accent-text",
  hold: "text-fg",
  sell: "text-danger",
  none: "text-fg-subtle",
};

function resolveRatingLabel(rating: FinalRating | null): string {
  if (rating === null) {
    return "—";
  }
  return ratingToLabel[rating];
}

function resolveRatingClass(rating: FinalRating | null): string {
  if (rating === null) {
    return "text-fg-subtle";
  }
  return ratingToAccent[rating];
}

const provenanceColumns: ColumnDef<SourceProvenance, unknown>[] = [
  {
    accessorKey: "provider",
    header: "Provider",
    cell: ({ getValue }) => (
      <span className="text-fg">{String(getValue<string>())}</span>
    ),
  },
  {
    accessorKey: "tool",
    header: "Tool",
    cell: ({ getValue }) => (
      <span className="text-fg-muted">{String(getValue<string>())}</span>
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
    accessorKey: "latency_ms",
    header: "Latency",
    meta: { numeric: true },
    cell: ({ getValue }) => (
      <span>{getValue<number>().toLocaleString()}</span>
    ),
  },
  {
    accessorKey: "sample_count",
    header: "Samples",
    meta: { numeric: true },
    cell: ({ getValue }) => (
      <span>{getValue<number>().toLocaleString()}</span>
    ),
  },
  {
    accessorKey: "as_of",
    header: "As-of",
    meta: { numeric: true },
    cell: ({ getValue }) => {
      const raw = getValue<string | null>();
      return <span>{raw ?? "—"}</span>;
    },
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ getValue }) => (
      <StatusDot
        status={provenanceStatusToStatusKind(
          getValue<SourceProvenance["status"]>(),
        )}
      />
    ),
  },
];

interface AnalystChipModel {
  key: string;
  label: string;
  status: StatusKind;
}

function buildAnalystChips(
  analystKeys: readonly string[],
  reports: readonly RunReport[],
): AnalystChipModel[] {
  const fulfilled = new Set<string>();
  for (const report of reports) {
    fulfilled.add(report.analyst);
  }
  const union = new Set<string>(analystKeys);
  for (const report of reports) {
    union.add(report.analyst);
  }
  const ordered = Array.from(union).sort(compareAnalysts);
  return ordered.map((key) => ({
    key,
    label: resolveAnalystLabel(key).toUpperCase(),
    status: fulfilled.has(key) ? "succeeded" : "pending",
  }));
}

function buildMetricTiles(detail: ResearchRunDetail): MetricTile[] {
  const debateDepth = readNumber(detail.config, "debate_depth");
  return [
    { label: "TOKENS USED", value: "—", sparkline: [] },
    {
      label: "TOOL CALLS",
      value: detail.provenance.length.toLocaleString(),
      sparkline: [],
    },
    {
      label: "DEBATE ROUNDS",
      value: debateDepth !== null ? debateDepth.toString() : "—",
      sparkline: [],
    },
    {
      label: "WALL CLOCK",
      value: formatWallClock(detail.wall_clock_ms),
      sparkline: [],
    },
  ];
}

export interface RunDetailProps {
  detail: ResearchRunDetail;
  macroBrief: MacroBriefPublic | null;
}

export function RunDetail(props: RunDetailProps): ReactElement {
  const { detail, macroBrief } = props;
  const isFunnelResearch = detail.strategy === "funnel_research";
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [optimisticStatus, setOptimisticStatus] = useState<RunStatus | null>(
    null,
  );

  const resolvedStatus = optimisticStatus ?? detail.status;
  const analystKeys = useMemo(
    () => readStringArray(detail.config, "analysts"),
    [detail.config],
  );
  const analystChips = useMemo(
    () => buildAnalystChips(analystKeys, detail.reports),
    [analystKeys, detail.reports],
  );
  const metricTiles = useMemo(() => buildMetricTiles(detail), [detail]);
  const initialLogLines = useMemo(
    () => mapEventsToLogLines(detail.events),
    [detail.events],
  );
  const reportOptions = useMemo(
    () =>
      detail.reports.map((report) => ({
        key: report.id,
        analyst: report.analyst,
        label: resolveAnalystLabel(report.analyst),
        markdown: report.markdown,
      })),
    [detail.reports],
  );
  const [activeReportId, setActiveReportId] = useState<string | null>(
    reportOptions[0]?.key ?? null,
  );
  const activeReport = useMemo(() => {
    if (activeReportId === null) {
      return null;
    }
    return reportOptions.find((option) => option.key === activeReportId) ?? null;
  }, [activeReportId, reportOptions]);
  const isCancellable =
    resolvedStatus === "queued" || resolvedStatus === "running";
  const isLogStreamTerminal = isTerminal(resolvedStatus);

  const handleOptimisticCancel = (): void => {
    setOptimisticStatus("cancelled");
  };
  const handleCancelRollback = (): void => {
    setOptimisticStatus(null);
  };

  return (
    <div className="max-w-[1400px] mx-auto">
      <header className="sticky top-0 z-10 bg-canvas border-b border-line">
        <div className="flex items-center gap-4 px-6 py-4">
          <span className="text-2xl font-mono tabular-nums text-fg">
            {detail.ticker ?? "—"}
          </span>
          <HexPill value={detail.id} />
          <StatusDot
            status={runStatusToStatusKind(resolvedStatus)}
            label={statusToLabel[resolvedStatus]}
          />
          <div className="flex-1" />
          {isFunnelResearch ? (
            <Button asChild size="sm" variant="ghost">
              <Link
                href={`/research/runs/${detail.id}/portfolio-brief` as Route}
              >
                PORTFOLIO BRIEF
              </Link>
            </Button>
          ) : null}
          {isCancellable ? (
            <CancelRunButton
              runId={detail.id}
              onOptimisticCancel={handleOptimisticCancel}
              onCancelRollback={handleCancelRollback}
            />
          ) : detail.ticker !== null ? (
            <RerunButton runId={detail.id} />
          ) : null}
        </div>
      </header>

      <div className="px-6 pt-4 pb-12">
        {isFunnelResearch && macroBrief !== null ? (
          <MacroBriefDetail data={macroBrief} />
        ) : isFunnelResearch &&
          (resolvedStatus === "failed" || resolvedStatus === "cancelled") ? (
          <p className="text-sm text-fg-muted">
            Macro brief was not produced because the run was {resolvedStatus}.
          </p>
        ) : isFunnelResearch ? (
          <p className="text-sm text-fg-muted">Macro brief is generating…</p>
        ) : (
          <Tabs
            value={activeTab}
            onValueChange={(next) => setActiveTab(next as TabKey)}
          >
            <TabsList>
              {tabConfigs.map((tab) => (
                <TabsTrigger key={tab.key} value={tab.key}>
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value="overview">
              <div className="flex flex-col gap-6">
                <MetricQuadrant tiles={metricTiles} />
                <Card>
                  <CardHeader>
                    <CardTitle>FINAL DECISION</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-baseline gap-4">
                      <span
                        className={cn(
                          "text-2xl font-mono tabular-nums",
                          resolveRatingClass(detail.final_rating),
                        )}
                      >
                        {resolveRatingLabel(detail.final_rating)}
                      </span>
                    </div>
                    <p className="mt-4 text-sm text-fg-muted leading-relaxed whitespace-pre-wrap">
                      {detail.final_decision_summary ?? "Decision pending."}
                    </p>
                    {analystChips.length > 0 ? (
                      <div className="mt-6 flex flex-wrap gap-4">
                        {analystChips.map((chip) => (
                          <StatusDot
                            key={chip.key}
                            status={chip.status}
                            label={chip.label}
                          />
                        ))}
                      </div>
                    ) : null}
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            <TabsContent value="reports">
              {reportOptions.length === 0 ? (
                <p className="text-sm text-fg-subtle py-6">
                  Reports will appear here as analysts finish.
                </p>
              ) : (
                <div className="flex gap-6">
                  <aside className="w-56 shrink-0">
                    <CapsLabel className="px-2 py-2 block">ANALYSTS</CapsLabel>
                    <ul className="flex flex-col">
                      {reportOptions.map((option) => {
                        const isActive = option.key === activeReportId;
                        return (
                          <li key={option.key}>
                            <button
                              type="button"
                              onClick={() => setActiveReportId(option.key)}
                              className={cn(
                                "w-full text-left px-2 py-2 text-sm transition-colors duration-150 border-l-2",
                                isActive
                                  ? "border-l-accent bg-surface-2 text-accent-text"
                                  : "border-l-transparent text-fg-muted hover:text-fg hover:bg-surface",
                              )}
                            >
                              {option.label}
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </aside>
                  <section className="flex-1 min-w-0 flex flex-col gap-6">
                    <CapsLabel>REPORT</CapsLabel>
                    {activeReport !== null ? (
                      <p className="text-sm text-fg leading-relaxed whitespace-pre-wrap">
                        {activeReport.markdown}
                      </p>
                    ) : (
                      <p className="text-sm text-fg-subtle">
                        Select a report to view its contents.
                      </p>
                    )}
                  </section>
                </div>
              )}
            </TabsContent>

            <TabsContent value="debate">
              <p className="text-sm text-fg-subtle py-6">
                Debate transcript not available for this run.
              </p>
            </TabsContent>

            <TabsContent value="risk">
              <p className="text-sm text-fg-subtle py-6">Risk check pending.</p>
            </TabsContent>

            <TabsContent value="logs">
              <RunLogStream
                runId={detail.id}
                initialLines={initialLogLines}
                isTerminal={isLogStreamTerminal}
              />
            </TabsContent>

            <TabsContent value="provenance">
              <DataTable<SourceProvenance>
                data={[...detail.provenance]}
                columns={provenanceColumns}
                getRowId={(row) => row.id}
              />
            </TabsContent>
          </Tabs>
        )}
      </div>
    </div>
  );
}
