"use client";

import { useState } from "react";
import type { ReactElement } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { toast } from "sonner";
import {
  ActivityStrip,
  Badge,
  Button,
  CapsLabel,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CodeBlock,
  CommandPalette,
  DataTable,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DetailRail,
  HexPill,
  HoldButton,
  Input,
  LogViewer,
  MetricQuadrant,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Sparkline,
  StatusPill,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui";
import type {
  BadgeVariant,
  ButtonSize,
  ButtonVariant,
  CommandItem,
  LogLine,
  MetricTile,
  StatusPillStatus,
} from "@/components/ui";
import { cn } from "@/lib/cn";
import { colorTokens } from "@/lib/tokens";

type ColorEntry = readonly [string, string];

const colorEntries: ColorEntry[] = [
  ["canvas", colorTokens.canvas],
  ["panel", colorTokens.panel],
  ["surface", colorTokens.surface],
  ["surface-2", colorTokens.surface2],
  ["line", colorTokens.line],
  ["line-strong", colorTokens.lineStrong],
  ["accent", colorTokens.accent],
  ["accent-soft", colorTokens.accentSoft],
  ["accent-deep", colorTokens.accentDeep],
  ["accent-press", colorTokens.accentPress],
  ["accent-text", colorTokens.accentText],
  ["warn", colorTokens.warn],
  ["danger", colorTokens.danger],
  ["success", colorTokens.success],
  ["fg", colorTokens.fg],
  ["fg-muted", colorTokens.fgMuted],
  ["fg-subtle", colorTokens.fgSubtle],
];

const buttonVariants: ButtonVariant[] = [
  "primary",
  "secondary",
  "tertiary",
  "default",
  "ghost",
  "link",
  "destructive",
];
const buttonSizes: ButtonSize[] = ["default", "sm"];

const statuses: StatusPillStatus[] = [
  "pending",
  "running",
  "succeeded",
  "failed",
  "cancelled",
  "paused",
];

const badgeVariants: BadgeVariant[] = ["buy", "hold", "sell", "none"];

const sampleSparkline = [12, 18, 14, 22, 26, 21, 29, 33, 31, 38, 36, 42];

const metricTiles: MetricTile[] = [
  {
    label: "Tokens Used",
    value: "25,251",
    sparkline: [10, 12, 14, 18, 22, 30, 28, 34, 41, 48],
  },
  {
    label: "Tool Calls",
    value: "142",
    sparkline: [4, 6, 8, 10, 9, 12, 14, 18, 22, 24],
  },
  {
    label: "Debate Rounds",
    value: "4",
    sparkline: [0, 1, 1, 2, 2, 3, 3, 4, 4, 4],
  },
  {
    label: "Wall Clock",
    value: "12m 38s",
    sparkline: [1, 2, 4, 5, 7, 9, 10, 12, 12, 12],
  },
];

interface RunRow {
  id: string;
  ticker: string;
  runId: string;
  tokens: number;
  durationSeconds: number;
  rating: BadgeVariant;
  status: StatusPillStatus;
}

const runRows: RunRow[] = [
  {
    id: "run-aapl-01",
    ticker: "AAPL",
    runId: "sb-aLPQ00ucncCYFz",
    tokens: 24812,
    durationSeconds: 742,
    rating: "buy",
    status: "succeeded",
  },
  {
    id: "run-msft-02",
    ticker: "MSFT",
    runId: "sb-bMSF11vdocDZGa",
    tokens: 31204,
    durationSeconds: 901,
    rating: "buy",
    status: "succeeded",
  },
  {
    id: "run-tsla-03",
    ticker: "TSLA",
    runId: "sb-cTSL22wepEAHb",
    tokens: 19488,
    durationSeconds: 612,
    rating: "sell",
    status: "succeeded",
  },
  {
    id: "run-nvda-04",
    ticker: "NVDA",
    runId: "sb-dNVD33xfqFBIc",
    tokens: 28911,
    durationSeconds: 833,
    rating: "buy",
    status: "running",
  },
  {
    id: "run-meta-05",
    ticker: "META",
    runId: "sb-eMTA44ygrGCJd",
    tokens: 22301,
    durationSeconds: 711,
    rating: "hold",
    status: "succeeded",
  },
  {
    id: "run-googl-06",
    ticker: "GOOGL",
    runId: "sb-fGGL55zhsHDKe",
    tokens: 26442,
    durationSeconds: 798,
    rating: "buy",
    status: "succeeded",
  },
  {
    id: "run-amzn-07",
    ticker: "AMZN",
    runId: "sb-gAMZ66aitIELf",
    tokens: 17621,
    durationSeconds: 540,
    rating: "none",
    status: "failed",
  },
  {
    id: "run-amd-08",
    ticker: "AMD",
    runId: "sb-hAMD77bjuJFMg",
    tokens: 21133,
    durationSeconds: 689,
    rating: "hold",
    status: "pending",
  },
];

const sampleLogs: LogLine[] = [
  {
    ts: "12:01:04.118",
    level: "info",
    message: "starting TradingAgentsGraph run sb-aLPQ00ucncCYFz",
  },
  {
    ts: "12:01:04.214",
    level: "info",
    message: "loading provider yfinance for AAPL",
  },
  {
    ts: "12:01:04.321",
    level: "info",
    message: "fetched 252 bars of OHLCV data",
  },
  { ts: "12:01:04.451", level: "info", message: "analyst.market.start" },
  {
    ts: "12:01:05.022",
    level: "warn",
    message: "rate limit approaching for finnhub (87/100)",
  },
  { ts: "12:01:05.612", level: "info", message: "analyst.news.start" },
  { ts: "12:01:06.214", level: "info", message: "analyst.fundamentals.start" },
  { ts: "12:01:07.118", level: "info", message: "analyst.social.start" },
  {
    ts: "12:01:08.221",
    level: "info",
    message: "researcher.bull.opening_stance complete",
  },
  {
    ts: "12:01:09.412",
    level: "info",
    message: "researcher.bear.opening_stance complete",
  },
  { ts: "12:01:10.118", level: "info", message: "debate.round.1.start" },
  {
    ts: "12:01:14.622",
    level: "warn",
    message: "tool_call timeout near limit (28s/30s)",
  },
  {
    ts: "12:01:15.001",
    level: "info",
    message: "debate.round.1.end winner=bull",
  },
  {
    ts: "12:01:16.214",
    level: "err",
    message: "provider polygon returned 5xx; falling back to yfinance",
  },
  { ts: "12:01:17.318", level: "info", message: "debate.round.2.start" },
  {
    ts: "12:01:21.514",
    level: "info",
    message: "debate.round.2.end winner=bull",
  },
  { ts: "12:01:22.612", level: "info", message: "risk_manager.evaluating" },
  { ts: "12:01:23.812", level: "info", message: "trader.composing_signal" },
  {
    ts: "12:01:24.913",
    level: "info",
    message: "final_decision rating=BUY confidence=0.71",
  },
  {
    ts: "12:01:25.118",
    level: "info",
    message: "run_completed wall_clock=12.4m",
  },
];

const sampleConfigSnippet = `# TradingAgents run configuration
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["deep_think_llm"] = "gpt-4o"
config["quick_think_llm"] = "gpt-4o-mini"
config["max_debate_rounds"] = 2
config["online_tools"] = True

graph = TradingAgentsGraph(debug=True, config=config)
state, decision = graph.propagate("AAPL", "2026-05-16")
print(decision)`;

const activityBuckets = [
  0, 1, 0, 2, 1, 3, 4, 6, 8, 12, 9, 7, 5, 6, 4, 3, 2, 2, 1, 1, 0, 0, 1, 0,
];

const commandItems: CommandItem[] = [
  {
    id: "ticker-aapl",
    label: "AAPL — Apple Inc",
    hint: "ticker",
    section: "tickers",
  },
  {
    id: "ticker-msft",
    label: "MSFT — Microsoft Corp",
    hint: "ticker",
    section: "tickers",
  },
  {
    id: "ticker-nvda",
    label: "NVDA — NVIDIA Corp",
    hint: "ticker",
    section: "tickers",
  },
  {
    id: "run-1",
    label: "sb-aLPQ00ucncCYFz",
    hint: "AAPL · 12:01",
    section: "runs",
  },
  {
    id: "run-2",
    label: "sb-bMSF11vdocDZGa",
    hint: "MSFT · 11:48",
    section: "runs",
  },
  {
    id: "report-1",
    label: "Q1 Earnings Recap",
    hint: "report",
    section: "reports",
  },
  {
    id: "settings-api",
    label: "API Keys",
    hint: "settings",
    section: "settings",
  },
];

interface SectionProps {
  title: string;
  description?: string;
  children: ReactElement | ReactElement[];
}

function Section(props: SectionProps): ReactElement {
  const { title, description, children } = props;
  return (
    <section className="border-t border-line pt-8 mt-8 first:border-0 first:mt-0 first:pt-0">
      <div className="mb-6 flex flex-col gap-1">
        <CapsLabel as="h2">{title}</CapsLabel>
        {description ? (
          <p className="text-sm text-fg-muted">{description}</p>
        ) : null}
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

const runColumns: ColumnDef<RunRow, unknown>[] = [
  {
    accessorKey: "ticker",
    header: "Ticker",
    cell: ({ row }) => (
      <span className="font-mono text-fg">{row.original.ticker}</span>
    ),
  },
  {
    accessorKey: "runId",
    header: "Run ID",
    cell: ({ row }) => <HexPill value={row.original.runId} />,
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusPill status={row.original.status} />,
  },
  {
    accessorKey: "tokens",
    header: "Tokens",
    meta: { numeric: true },
    cell: ({ row }) => <span>{row.original.tokens.toLocaleString()}</span>,
  },
  {
    accessorKey: "durationSeconds",
    header: "Duration",
    meta: { numeric: true },
    cell: ({ row }) => {
      const total = row.original.durationSeconds;
      const minutes = Math.floor(total / 60);
      const seconds = total % 60;
      return (
        <span>
          {minutes}m {seconds.toString().padStart(2, "0")}s
        </span>
      );
    },
  },
  {
    accessorKey: "rating",
    header: "Rating",
    meta: { numeric: true },
    cell: ({ row }) => (
      <span className="inline-flex justify-end">
        <Badge variant={row.original.rating} />
      </span>
    ),
  },
];

export default function DesignSystemPage(): ReactElement {
  const [activeTab, setActiveTab] = useState<string>("overview");
  const [selectedRowId, setSelectedRowId] = useState<string | undefined>(
    "run-msft-02",
  );
  const [isRailOpen, setIsRailOpen] = useState(false);

  return (
    <TooltipProvider delayDuration={400}>
      <main className="relative mx-auto max-w-[1400px] px-8 py-10">
        <header className="mb-10 flex flex-col gap-2">
          <CapsLabel>Alphora · Internal</CapsLabel>
          <h1 className="text-2xl font-medium tracking-[-0.03em] text-fg">
            Design System
          </h1>
          <p className="text-sm text-fg-muted">
            Cosmic-lilac instrument-panel primitives. Press{" "}
            <span className="font-mono text-fg">⌘K</span> for the command
            palette.
          </p>
        </header>

        <Section
          title="Colors"
          description="Token swatches, mapped to Tailwind utilities."
        >
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
            {colorEntries.map(([name, hex]) => (
              <div
                key={name}
                className="flex flex-col gap-2 rounded-md border border-line bg-surface p-3"
              >
                <span
                  className="h-12 w-full rounded-sm border border-line"
                  style={{ backgroundColor: hex }}
                  aria-hidden="true"
                />
                <div className="flex flex-col gap-0.5">
                  <span className="text-xs text-fg">{name}</span>
                  <span className="font-mono text-[11px] text-fg-subtle">
                    {hex}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Section>

        <Section
          title="Typography"
          description="Geist sans and Geist mono across the scale."
        >
          <div className="flex flex-col gap-3">
            <span className="text-2xl font-medium tracking-[-0.03em] text-fg">
              Page Title — 22px
            </span>
            <span className="text-lg text-fg">Card Title — 17px</span>
            <span className="text-base text-fg">Body Emphasis — 15.5px</span>
            <span className="text-sm text-fg">Body — 14px</span>
            <span className="text-xs text-fg-muted">
              Helper / Timestamp — 12px
            </span>
            <CapsLabel>Section Caps — 11px tracked</CapsLabel>
            <span className="font-mono text-sm tabular-nums text-fg">
              182.47 -1.42 (-0.77%) — Geist Mono Tabular
            </span>
          </div>
        </Section>

        <Section
          title="Buttons"
          description="Variant × size matrix with press scale."
        >
          <div className="space-y-4">
            {buttonSizes.map((size) => (
              <div key={size} className="flex flex-wrap items-center gap-3">
                <CapsLabel className="w-16">{size}</CapsLabel>
                {buttonVariants.map((variant) => (
                  <Button key={variant} variant={variant} size={size}>
                    {variant}
                  </Button>
                ))}
                <Button variant="primary" size={size} disabled>
                  disabled
                </Button>
              </div>
            ))}
          </div>
        </Section>

        <Section
          title="Inputs & Selects"
          description="Form primitives with focus and disabled states."
        >
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="flex flex-col gap-2">
              <CapsLabel>Default</CapsLabel>
              <Input placeholder="Ticker symbol" />
            </div>
            <div className="flex flex-col gap-2">
              <CapsLabel>Pre-filled</CapsLabel>
              <Input defaultValue="AAPL" />
            </div>
            <div className="flex flex-col gap-2">
              <CapsLabel>Disabled</CapsLabel>
              <Input defaultValue="—" disabled />
            </div>
            <div className="flex flex-col gap-2">
              <CapsLabel>Select</CapsLabel>
              <Select defaultValue="openai">
                <SelectTrigger>
                  <SelectValue placeholder="LLM provider" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="openai">OpenAI · gpt-4o</SelectItem>
                  <SelectItem value="anthropic">
                    Anthropic · claude-opus
                  </SelectItem>
                  <SelectItem value="google">Google · gemini-2.5</SelectItem>
                  <SelectItem value="deepseek">DeepSeek · v3</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </Section>

        <Section title="Status Pills" description="All six status semantics.">
          <div className="flex flex-wrap items-center gap-3">
            {statuses.map((status) => (
              <StatusPill key={status} status={status} />
            ))}
          </div>
        </Section>

        <Section
          title="Badges"
          description="Rating chips for research-run rows."
        >
          <div className="flex flex-wrap items-center gap-3">
            {badgeVariants.map((variant) => (
              <Badge key={variant} variant={variant} />
            ))}
          </div>
        </Section>

        <Section title="Hex Pills" description="Hashes and run identifiers.">
          <div className="flex flex-wrap items-center gap-3">
            <HexPill value="sb-aLPQ00ucncCYFzzZ0qiNoL" />
            <HexPill value="f4a92e1c" />
            <HexPill value="run-2026-05-16T12:01" />
          </div>
        </Section>

        <Section title="Cards" description="Bg-surface card with caps title.">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Final Decision</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <span className="text-fg">AAPL</span>
                  <Badge variant="buy" />
                </div>
                <div className="mt-2 font-mono text-xs text-fg-muted">
                  confidence 0.71 · 2026-05-16
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Active Run</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <HexPill value="sb-dNVD33xfqFBIc" />
                  <StatusPill status="running" />
                </div>
                <div className="mt-2 font-mono text-xs text-fg-muted">
                  NVDA · 12m 38s wall clock
                </div>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Tabs"
          description="Animated lilac underline via layoutId spring."
        >
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList>
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="reports">Reports</TabsTrigger>
              <TabsTrigger value="debate">Debate</TabsTrigger>
              <TabsTrigger value="risk">Risk</TabsTrigger>
              <TabsTrigger value="logs">Logs</TabsTrigger>
              <TabsTrigger value="provenance">Provenance</TabsTrigger>
            </TabsList>
            <TabsContent value="overview">
              <p className="text-sm text-fg-muted">
                Overview tab — run-health quadrant and final decision live here.
              </p>
            </TabsContent>
            <TabsContent value="reports">
              <p className="text-sm text-fg-muted">
                Analyst markdown reports with the §8.8 code-block treatment.
              </p>
            </TabsContent>
            <TabsContent value="debate">
              <p className="text-sm text-fg-muted">
                Bull and bear transcript, animated when new rounds arrive.
              </p>
            </TabsContent>
            <TabsContent value="risk">
              <p className="text-sm text-fg-muted">
                Risk-manager evaluation and scenario stress fields.
              </p>
            </TabsContent>
            <TabsContent value="logs">
              <p className="text-sm text-fg-muted">
                Mono terminal log viewer, full-bleed.
              </p>
            </TabsContent>
            <TabsContent value="provenance">
              <p className="text-sm text-fg-muted">
                Provider/tool calls, latency, sample counts.
              </p>
            </TabsContent>
          </Tabs>
        </Section>

        <Section
          title="Data Table"
          description="Sortable rows with mono numerics and a selected-row rail."
        >
          <div className="rounded-xl border border-line bg-surface overflow-hidden">
            <DataTable
              data={runRows}
              columns={runColumns}
              selectedRowId={selectedRowId}
              onRowClick={(row) => setSelectedRowId(row.id)}
              getRowId={(row) => row.id}
            />
          </div>
        </Section>

        <Section
          title="Log Viewer"
          description="Bg-canvas, three columns, follow toggle."
        >
          <LogViewer lines={sampleLogs} />
        </Section>

        <Section
          title="Code Block"
          description="Lilac top border, traffic lights, optional copy."
        >
          <CodeBlock lang="python">{sampleConfigSnippet}</CodeBlock>
        </Section>

        <Section title="Metric Quadrant" description="Run-health 4-up grid.">
          <MetricQuadrant tiles={metricTiles} />
        </Section>

        <Section
          title="Sparkline"
          description="Inline trend, no animation by default."
        >
          <div className="flex items-center gap-6">
            <Sparkline data={sampleSparkline} />
            <Sparkline
              data={sampleSparkline.slice().reverse()}
              width={180}
              height={48}
            />
          </div>
        </Section>

        <Section
          title="Activity Strip"
          description="24-hour bucket histogram, lilac bars."
        >
          <div className="rounded-md border border-line bg-surface px-3 py-3 inline-block">
            <ActivityStrip
              buckets={activityBuckets}
              startTimestampIso="2026-05-16T00:00:00.000Z"
            />
          </div>
        </Section>

        <Section
          title="Command Palette"
          description="⌘K opens; sections for tickers, runs, reports, settings."
        >
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="default"
              onClick={() => {
                window.dispatchEvent(
                  new KeyboardEvent("keydown", { key: "k", metaKey: true }),
                );
              }}
            >
              Open palette (⌘K)
            </Button>
            <span className="text-sm text-fg-muted">
              Or press <span className="font-mono text-fg">⌘K</span> anywhere.
            </span>
          </div>
        </Section>

        <Section
          title="Dialog"
          description="Centered overlay for run-config / order tickets."
        >
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="primary">Open dialog</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Run TradingAgents</DialogTitle>
                <DialogDescription>
                  Confirm the configuration before launching the graph.
                </DialogDescription>
              </DialogHeader>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="flex flex-col gap-1">
                  <CapsLabel>Ticker</CapsLabel>
                  <span className="font-mono text-fg">AAPL</span>
                </div>
                <div className="flex flex-col gap-1">
                  <CapsLabel>Debate rounds</CapsLabel>
                  <span className="font-mono text-fg">2</span>
                </div>
              </div>
              <DialogFooter>
                <DialogClose asChild>
                  <Button variant="ghost">Cancel</Button>
                </DialogClose>
                <Button variant="primary">Launch</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </Section>

        <Section
          title="Tooltips"
          description="400ms delay, mono content, no glow."
        >
          <div className="flex flex-wrap items-center gap-4">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="default">Hover me</Button>
              </TooltipTrigger>
              <TooltipContent>2026-05-16 · 12:01:24</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost">Inline action</Button>
              </TooltipTrigger>
              <TooltipContent>0.34s · 1,204 tokens</TooltipContent>
            </Tooltip>
          </div>
        </Section>

        <Section
          title="Detail Rail"
          description="360px right rail, sticky, slide-in."
        >
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="default" onClick={() => setIsRailOpen(true)}>
              Open rail
            </Button>
            <span className="text-sm text-fg-muted">
              Closes from inside the rail.
            </span>
          </div>
          <div
            className={cn(
              "relative mt-4 rounded-md border border-line overflow-hidden",
              isRailOpen ? "min-h-[260px]" : "min-h-[120px]",
            )}
          >
            <div className="flex">
              <div className="flex-1 bg-canvas p-6">
                <p className="text-sm text-fg-muted">
                  Page content stays put. The rail slides in from the right.
                </p>
              </div>
              <DetailRail
                open={isRailOpen}
                onClose={() => setIsRailOpen(false)}
                title="Run Preview"
              >
                <div className="flex flex-col gap-4">
                  <HexPill value="sb-aLPQ00ucncCYFz" />
                  <div className="flex flex-col gap-1">
                    <CapsLabel>Ticker</CapsLabel>
                    <span className="text-fg">AAPL</span>
                  </div>
                  <div className="flex flex-col gap-1">
                    <CapsLabel>Status</CapsLabel>
                    <StatusPill status="succeeded" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <CapsLabel>Rating</CapsLabel>
                    <Badge variant="buy" />
                  </div>
                </div>
              </DetailRail>
            </div>
          </div>
        </Section>

        <Section
          title="Hold Button"
          description="Press-and-hold 1.2s to confirm."
        >
          <div className="flex flex-wrap items-center gap-4">
            <HoldButton
              label="Run TradingAgents"
              onComplete={() => toast.success("Run TradingAgents fired")}
            />
            <span className="text-sm text-fg-muted">
              Release early to cancel; complete fires the callback.
            </span>
          </div>
        </Section>

        <CommandPalette items={commandItems} />
      </main>
    </TooltipProvider>
  );
}
