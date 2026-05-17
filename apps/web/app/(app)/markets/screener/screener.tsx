"use client";

import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent, ReactElement } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import {
  Button,
  CapsLabel,
  DataTable,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Sparkline,
} from "@/components/ui";
import { sampleTickers } from "@/lib/fixtures/tickers";
import type { TickerRow } from "@/lib/fixtures/tickers";
import { useAppShellRail } from "@/components/shell/app-shell";

type UniverseKey = "sp500" | "nasdaq100" | "watchlist";

interface UniverseOption {
  key: UniverseKey;
  label: string;
}

const universeOptions: readonly UniverseOption[] = [
  { key: "sp500", label: "S&P 500" },
  { key: "nasdaq100", label: "Nasdaq 100" },
  { key: "watchlist", label: "Watchlist" },
];

type FactorKey =
  | "quality"
  | "valuation"
  | "momentum"
  | "volatility"
  | "sentiment";

interface FactorConfig {
  key: FactorKey;
  label: string;
  initialWeight: number;
}

const factorConfigs: readonly FactorConfig[] = [
  { key: "quality", label: "QUALITY", initialWeight: 0.4 },
  { key: "valuation", label: "VALUATION", initialWeight: 0.3 },
  { key: "momentum", label: "MOMENTUM", initialWeight: 0.5 },
  { key: "volatility", label: "VOLATILITY", initialWeight: 0.2 },
  { key: "sentiment", label: "SENTIMENT", initialWeight: 0.3 },
];

function formatPrice(value: number): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatScore(value: number): string {
  return value.toFixed(2);
}

const columns: ColumnDef<TickerRow, unknown>[] = [
  {
    accessorKey: "ticker",
    header: "Ticker",
    cell: ({ getValue }) => (
      <span className="font-mono text-fg">{String(getValue<string>())}</span>
    ),
  },
  {
    accessorKey: "name",
    header: "Name",
    cell: ({ getValue }) => (
      <span className="text-fg-muted">{String(getValue<string>())}</span>
    ),
  },
  {
    accessorKey: "price",
    header: "Price",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{formatPrice(getValue<number>())}</span>,
  },
  {
    accessorKey: "score",
    header: "Score",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{formatScore(getValue<number>())}</span>,
  },
  {
    accessorKey: "quality",
    header: "Quality",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{formatScore(getValue<number>())}</span>,
  },
  {
    accessorKey: "valuation",
    header: "Valuation",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{formatScore(getValue<number>())}</span>,
  },
  {
    accessorKey: "momentum",
    header: "Momentum",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{formatScore(getValue<number>())}</span>,
  },
];

interface PromotePanelProps {
  ticker: TickerRow;
}

function PromotePanel(props: PromotePanelProps): ReactElement {
  const { ticker } = props;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <span className="text-2xl font-mono tabular-nums text-fg">
          {ticker.ticker}
        </span>
        <span className="text-xs text-fg-muted">{ticker.name}</span>
      </div>
      <div className="flex items-baseline gap-3">
        <span className="font-mono tabular-nums text-base text-fg">
          {formatPrice(ticker.price)}
        </span>
        <span
          className={
            ticker.dayPct >= 0
              ? "font-mono text-xs text-accent-text"
              : "font-mono text-xs text-danger"
          }
        >
          {ticker.dayPct >= 0 ? "+" : ""}
          {ticker.dayPct.toFixed(2)}%
        </span>
      </div>
      <Sparkline data={[...ticker.priceHistory]} width="100%" height={64} />
      <Button variant="primary" className="w-full">
        Promote to Run →
      </Button>
    </div>
  );
}

export function Screener(): ReactElement {
  const [universe, setUniverse] = useState<UniverseKey>("sp500");
  const [factorWeights, setFactorWeights] = useState<Record<FactorKey, number>>(
    () =>
      factorConfigs.reduce<Record<FactorKey, number>>(
        (acc, config) => {
          acc[config.key] = config.initialWeight;
          return acc;
        },
        {
          quality: 0,
          valuation: 0,
          momentum: 0,
          volatility: 0,
          sentiment: 0,
        },
      ),
  );
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const { setRail, closeRail } = useAppShellRail();

  const rows = useMemo(() => [...sampleTickers], []);

  useEffect(() => {
    if (!selectedTicker) {
      return;
    }
    const match = rows.find((row) => row.ticker === selectedTicker);
    if (!match) {
      return;
    }
    setRail({
      title: `${match.ticker} preview`,
      body: <PromotePanel ticker={match} />,
    });
  }, [selectedTicker, rows, setRail]);

  useEffect(() => {
    return () => {
      closeRail();
    };
  }, [closeRail]);

  const handleSliderChange =
    (key: FactorKey) =>
    (event: ChangeEvent<HTMLInputElement>): void => {
      const next = Number(event.target.value) / 100;
      setFactorWeights((prev) => ({ ...prev, [key]: next }));
    };

  return (
    <div className="flex h-full min-h-0">
      <aside className="w-72 shrink-0 border-r border-line px-4 py-6 overflow-y-auto">
        <CapsLabel className="block mb-2">UNIVERSE</CapsLabel>
        <Select value={universe} onValueChange={(next) => setUniverse(next as UniverseKey)}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {universeOptions.map((option) => (
              <SelectItem key={option.key} value={option.key}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <CapsLabel className="block mt-8 mb-2">FACTORS</CapsLabel>
        <div className="flex flex-col gap-4">
          {factorConfigs.map((factor) => {
            const value = factorWeights[factor.key];
            return (
              <div key={factor.key} className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <CapsLabel>{factor.label}</CapsLabel>
                  <span className="font-mono tabular-nums text-xs text-fg">
                    {value.toFixed(2)}
                  </span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={Math.round(value * 100)}
                  onChange={handleSliderChange(factor.key)}
                  aria-label={factor.label}
                  className="w-full h-1.5 rounded-md bg-surface border border-line appearance-none cursor-pointer"
                  style={{ accentColor: "var(--color-accent)" }}
                />
              </div>
            );
          })}
        </div>
      </aside>

      <section className="flex-1 min-w-0 overflow-y-auto">
        <div className="px-6 py-6">
          <DataTable<TickerRow>
            data={rows}
            columns={columns}
            getRowId={(row) => row.ticker}
            selectedRowId={selectedTicker ?? undefined}
            onRowClick={(row) => setSelectedTicker(row.ticker)}
          />
        </div>
      </section>
    </div>
  );
}
