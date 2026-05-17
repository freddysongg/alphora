"use client";

import { useState } from "react";
import type { ReactElement } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import {
  CapsLabel,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CodeBlock,
  DataTable,
  HexPill,
  HoldButton,
  LogViewer,
  MetricQuadrant,
  StatusDot,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui";
import type { MetricTile, StatusKind } from "@/components/ui";
import { sampleLogLines } from "@/lib/fixtures/logs";
import { cn } from "@/lib/cn";

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

const sampleSpark = [3, 4, 6, 5, 8, 9, 12, 14, 11, 13, 18, 22, 19, 24, 21, 28];

const metricTiles: readonly MetricTile[] = [
  { label: "TOKENS USED", value: "25,251", sparkline: sampleSpark },
  { label: "TOOL CALLS", value: "142", sparkline: sampleSpark.slice().reverse() },
  { label: "DEBATE ROUNDS", value: "4", sparkline: [1, 1, 2, 2, 3, 3, 4, 4] },
  { label: "WALL CLOCK", value: "12m 38s", sparkline: sampleSpark },
];

type AnalystKey =
  | "bull"
  | "bear"
  | "macro"
  | "fundamentals"
  | "sentiment";

interface AnalystChip {
  key: AnalystKey;
  label: string;
  status: StatusKind;
}

const analystChips: readonly AnalystChip[] = [
  { key: "bull", label: "BULL", status: "succeeded" },
  { key: "bear", label: "BEAR", status: "failed" },
  { key: "macro", label: "MACRO", status: "succeeded" },
  { key: "fundamentals", label: "FUNDAMENTALS", status: "succeeded" },
  { key: "sentiment", label: "SENTIMENT", status: "succeeded" },
];

type ReportAnalyst =
  | "bull"
  | "bear"
  | "macro"
  | "fundamentals"
  | "sentiment"
  | "risk";

interface ReportPaneOption {
  key: ReportAnalyst;
  label: string;
}

const reportOptions: readonly ReportPaneOption[] = [
  { key: "bull", label: "Bull" },
  { key: "bear", label: "Bear" },
  { key: "macro", label: "Macro" },
  { key: "fundamentals", label: "Fundamentals" },
  { key: "sentiment", label: "Sentiment" },
  { key: "risk", label: "Risk" },
];

interface DebateMessage {
  speaker: "BULL" | "BEAR";
  body: string;
}

const debateMessages: readonly DebateMessage[] = [
  {
    speaker: "BULL",
    body: "Operating leverage from services is masked by hardware seasonality. With installed base near 2.2B active devices and services margin holding above 70%, the multiple compresses long before earnings power compresses.",
  },
  {
    speaker: "BEAR",
    body: "Greater China revenue declined low-double-digits y/y and gross margin help from mix is already priced into 28x forward earnings. A reset toward 22x is more defensible than calling for upside re-rating.",
  },
  {
    speaker: "BULL",
    body: "iPhone unit estimates are conservative against the 17 cycle; Apple Intelligence likely drives a 6-9% upgrade pull-forward across the installed base over four quarters.",
  },
  {
    speaker: "BEAR",
    body: "On-device AI is a feature, not a revenue line. Capex on silicon doesn't fix that gross margin expansion past 46% requires services growth that may decelerate.",
  },
];

interface RiskItem {
  label: string;
  status: StatusKind;
  detail: string;
}

const riskItems: readonly RiskItem[] = [
  {
    label: "Liquidity check",
    status: "succeeded",
    detail: "ADV > 50M shares, slippage budget < 2 bps at 0.1% participation",
  },
  {
    label: "Concentration",
    status: "succeeded",
    detail: "Position sizing 4.2% of equity, within 8% policy band",
  },
  {
    label: "Headline risk",
    status: "failed",
    detail: "Open DOJ investigation reported 2026-04-22, unresolved",
  },
  {
    label: "Earnings proximity",
    status: "stale",
    detail: "Last refresh 18h ago; calendar data older than threshold",
  },
];

interface ProvenanceRow {
  id: string;
  provider: string;
  tool: string;
  ticker: string;
  latencyMs: number;
  samples: number;
  asOf: string;
  status: StatusKind;
}

const provenanceRows: readonly ProvenanceRow[] = [
  { id: "p1", provider: "yfinance", tool: "price", ticker: "AAPL", latencyMs: 412, samples: 1820, asOf: "2026-05-16T14:32:02Z", status: "succeeded" },
  { id: "p2", provider: "yfinance", tool: "indicators", ticker: "AAPL", latencyMs: 484, samples: 1820, asOf: "2026-05-16T14:32:03Z", status: "succeeded" },
  { id: "p3", provider: "alphavantage", tool: "fundamentals", ticker: "AAPL", latencyMs: 894, samples: 240, asOf: "2026-05-16T14:31:42Z", status: "succeeded" },
  { id: "p4", provider: "yahoo-news", tool: "news", ticker: "AAPL", latencyMs: 687, samples: 142, asOf: "2026-05-16T14:32:03Z", status: "succeeded" },
  { id: "p5", provider: "reddit", tool: "sentiment", ticker: "AAPL", latencyMs: 1142, samples: 36, asOf: "2026-05-16T14:32:05Z", status: "succeeded" },
  { id: "p6", provider: "alphavantage", tool: "insider", ticker: "AAPL", latencyMs: 5021, samples: 0, asOf: "2026-05-16T14:32:11Z", status: "failed" },
  { id: "p7", provider: "stocktwits", tool: "sentiment", ticker: "AAPL", latencyMs: 824, samples: 412, asOf: "2026-05-16T13:58:00Z", status: "stale" },
  { id: "p8", provider: "yfinance", tool: "insider", ticker: "AAPL", latencyMs: 1240, samples: 18, asOf: "2026-05-15T22:14:00Z", status: "stale" },
];

const provenanceColumns: ColumnDef<ProvenanceRow, unknown>[] = [
  { accessorKey: "provider", header: "Provider", cell: ({ getValue }) => <span className="text-fg">{String(getValue<string>())}</span> },
  { accessorKey: "tool", header: "Tool", cell: ({ getValue }) => <span className="text-fg-muted">{String(getValue<string>())}</span> },
  { accessorKey: "ticker", header: "Ticker", cell: ({ getValue }) => <span className="font-mono text-fg">{String(getValue<string>())}</span> },
  { accessorKey: "latencyMs", header: "Latency", meta: { numeric: true }, cell: ({ getValue }) => <span>{getValue<number>().toLocaleString()}</span> },
  { accessorKey: "samples", header: "Samples", meta: { numeric: true }, cell: ({ getValue }) => <span>{getValue<number>().toLocaleString()}</span> },
  { accessorKey: "asOf", header: "As-of", meta: { numeric: true }, cell: ({ getValue }) => <span>{String(getValue<string>())}</span> },
  { accessorKey: "status", header: "Status", cell: ({ getValue }) => <StatusDot status={getValue<StatusKind>()} /> },
];

const sampleReportBody = `Apple's services segment continued to expand share of total revenue, reaching an estimated 28% in the trailing twelve months. App Store + subscription bundles + advertising are now the dominant marginal contributors, and the operating leverage they imply is structurally underappreciated in consensus models that anchor on iPhone unit volume.

We modeled a 6-9% upgrade pull-forward across the installed base over four quarters once Apple Intelligence reaches general availability, which is plausible given prior super-cycle benchmarks. The base case still requires services growth at or above 14% y/y; a downside case where services decelerate to 9% would compress the multiple back toward the 5-year mean.`;

const sampleSnippet = `from tradingagents.graph import TradingAgentsGraph

graph = TradingAgentsGraph(
    analysts=["bull", "bear", "macro", "fundamentals", "sentiment"],
    config=default_config(),
)
state = graph.propagate(ticker="AAPL", trade_date="2026-05-16")`;

export interface RunDetailProps {
  runId: string;
  ticker: string;
}

export function RunDetail(props: RunDetailProps): ReactElement {
  const { runId, ticker } = props;
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [activeAnalyst, setActiveAnalyst] = useState<ReportAnalyst>("bull");

  const handleHoldComplete = (): void => {
    // Hold-to-execute stub: real implementation enqueues a new run.
  };

  return (
    <div className="max-w-[1400px] mx-auto">
      <header className="sticky top-0 z-10 bg-canvas border-b border-line">
        <div className="flex items-center gap-4 px-6 py-4">
          <span className="text-2xl font-mono tabular-nums text-fg">
            {ticker}
          </span>
          <HexPill value={runId} />
          <StatusDot status="succeeded" label="SUCCEEDED" />
          <div className="flex-1" />
          <HoldButton label="run again" onComplete={handleHoldComplete} />
        </div>
      </header>

      <div className="px-6 pt-4 pb-12">
        <Tabs value={activeTab} onValueChange={(next) => setActiveTab(next as TabKey)}>
          <TabsList>
            {tabConfigs.map((tab) => (
              <TabsTrigger key={tab.key} value={tab.key}>
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>

          <TabsContent value="overview">
            <div className="flex flex-col gap-6">
              <MetricQuadrant tiles={[...metricTiles]} />
              <Card>
                <CardHeader>
                  <CardTitle>FINAL DECISION</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-baseline gap-4">
                    <span className="text-2xl font-mono tabular-nums text-accent-text">BUY</span>
                    <span className="text-xs text-fg-muted">confidence 0.78</span>
                  </div>
                  <p className="mt-4 text-sm text-fg-muted leading-relaxed">
                    Services momentum and installed-base leverage support a constructive 12-month view despite near-term China weakness. Position sizing capped at policy band; revisit on the next earnings print.
                  </p>
                  <div className="mt-6 flex flex-wrap gap-4">
                    {analystChips.map((chip) => (
                      <StatusDot key={chip.key} status={chip.status} label={chip.label} />
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="reports">
            <div className="flex gap-6">
              <aside className="w-56 shrink-0">
                <CapsLabel className="px-2 py-2 block">ANALYSTS</CapsLabel>
                <ul className="flex flex-col">
                  {reportOptions.map((option) => {
                    const isActive = option.key === activeAnalyst;
                    return (
                      <li key={option.key}>
                        <button
                          type="button"
                          onClick={() => setActiveAnalyst(option.key)}
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
                <p className="text-sm text-fg leading-relaxed whitespace-pre-wrap">
                  {sampleReportBody}
                </p>
                <CodeBlock lang="python">{sampleSnippet}</CodeBlock>
              </section>
            </div>
          </TabsContent>

          <TabsContent value="debate">
            <div className="flex flex-col gap-3">
              {debateMessages.map((message, index) => (
                <div
                  key={`debate-${index}`}
                  className="bg-surface border border-line rounded-xl p-4 shadow-[var(--shadow-card)]"
                >
                  <CapsLabel className="text-accent-text">
                    {message.speaker}
                  </CapsLabel>
                  <p className="mt-2 text-sm text-fg leading-relaxed">
                    {message.body}
                  </p>
                </div>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="risk">
            <Card>
              <CardHeader>
                <CardTitle>RISK CHECK</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="flex flex-col">
                  {riskItems.map((item) => (
                    <li
                      key={item.label}
                      className="flex items-start justify-between gap-4 py-3 border-b border-line/60 last:border-b-0"
                    >
                      <div className="flex flex-col gap-1">
                        <span className="text-sm text-fg">{item.label}</span>
                        <span className="text-xs text-fg-muted">{item.detail}</span>
                      </div>
                      <StatusDot status={item.status} />
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="logs">
            <LogViewer lines={[...sampleLogLines]} />
          </TabsContent>

          <TabsContent value="provenance">
            <DataTable<ProvenanceRow>
              data={[...provenanceRows]}
              columns={provenanceColumns}
              getRowId={(row) => row.id}
            />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
