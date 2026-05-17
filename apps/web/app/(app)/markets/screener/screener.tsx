"use client";

import { useActionState, useEffect, useMemo, useState } from "react";
import type { ChangeEvent, ReactElement } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useFormStatus } from "react-dom";
import { toast } from "sonner";
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
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui";
import { useAppShellRail } from "@/components/shell/app-shell";
import type { components } from "@/lib/api";
import {
  FACTOR_KEYS,
  WEIGHT_FIELD_PREFIX,
  recordToWeights,
} from "@/lib/screener/parse-weights";
import type { FactorKey, FactorWeights } from "@/lib/screener/parse-weights";
import { initialRunScreenerState, runScreener } from "./actions";

type ScreenerRunResponse = components["schemas"]["ScreenerRunResponse"];
type ScreenerResult = components["schemas"]["ScreenerResultPublic"];
type UniverseKey = components["schemas"]["ScreenerUniverseEnum"];

interface UniverseOption {
  key: UniverseKey;
  label: string;
  isDisabled: boolean;
  disabledReason?: string;
}

const universeOptions: readonly UniverseOption[] = [
  { key: "sp500", label: "S&P 500", isDisabled: false },
  { key: "nasdaq100", label: "Nasdaq 100", isDisabled: false },
  {
    key: "watchlist",
    label: "Watchlist",
    isDisabled: true,
    disabledReason: "Select a watchlist in Watchlists first.",
  },
];

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

const EM_DASH = "—";

function defaultWeightsFromConfig(): FactorWeights {
  return {
    quality: 0,
    valuation: 0,
    momentum: 0,
    volatility: 0,
    sentiment: 0,
    ...Object.fromEntries(
      factorConfigs.map((config) => [config.key, config.initialWeight]),
    ),
  };
}

function formatScore(value: number): string {
  return value.toFixed(2);
}

function factorCellValue(
  factorScores: Readonly<Record<string, number>>,
  key: FactorKey,
): string {
  const raw = factorScores[key];
  if (typeof raw !== "number" || !Number.isFinite(raw)) {
    return EM_DASH;
  }
  return formatScore(raw);
}

const resultColumns: ColumnDef<ScreenerResult, unknown>[] = [
  {
    accessorKey: "ticker",
    header: "Ticker",
    cell: ({ getValue }) => (
      <span className="font-mono text-fg">{String(getValue<string>())}</span>
    ),
  },
  {
    id: "name",
    header: "Name",
    cell: () => <span className="text-fg-muted">{EM_DASH}</span>,
  },
  {
    id: "price",
    header: "Price",
    meta: { numeric: true },
    cell: () => <span className="text-fg-muted">{EM_DASH}</span>,
  },
  {
    accessorKey: "score",
    header: "Score",
    meta: { numeric: true },
    cell: ({ getValue }) => <span>{formatScore(getValue<number>())}</span>,
  },
  {
    id: "quality",
    header: "Quality",
    meta: { numeric: true },
    cell: ({ row }) => (
      <span>{factorCellValue(row.original.factor_scores, "quality")}</span>
    ),
  },
  {
    id: "valuation",
    header: "Valuation",
    meta: { numeric: true },
    cell: ({ row }) => (
      <span>{factorCellValue(row.original.factor_scores, "valuation")}</span>
    ),
  },
  {
    id: "momentum",
    header: "Momentum",
    meta: { numeric: true },
    cell: ({ row }) => (
      <span>{factorCellValue(row.original.factor_scores, "momentum")}</span>
    ),
  },
];

interface PromotePanelProps {
  ticker: string;
}

function PromotePanel(props: PromotePanelProps): ReactElement {
  const { ticker } = props;
  const href = `/research/runs?ticker=${ticker}` as Route;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <span className="text-2xl font-mono tabular-nums text-fg">
          {ticker}
        </span>
        <span className="text-xs text-fg-muted">{EM_DASH}</span>
      </div>
      <Button asChild variant="primary" className="w-full">
        {/* follow-up: New Run dialog should prefill ticker from `?ticker=` query param */}
        <Link href={href}>Promote to Run →</Link>
      </Button>
    </div>
  );
}

interface SubmitButtonProps {
  isDisabled: boolean;
}

function SubmitButton(props: SubmitButtonProps): ReactElement {
  const { isDisabled } = props;
  const { pending } = useFormStatus();
  return (
    <Button
      type="submit"
      variant="primary"
      className="w-full"
      disabled={isDisabled || pending}
    >
      {pending ? "Running…" : "Run screener"}
    </Button>
  );
}

export interface ScreenerProps {
  initialRun: ScreenerRunResponse | null;
  loadError: string | null;
}

export function Screener(props: ScreenerProps): ReactElement {
  const { initialRun, loadError } = props;
  const initialUniverse: UniverseKey =
    initialRun !== null && isUniverseKey(initialRun.screener_run.universe)
      ? initialRun.screener_run.universe
      : "sp500";
  const initialWeights: FactorWeights =
    initialRun !== null
      ? recordToWeights(initialRun.screener_run.factor_weights)
      : defaultWeightsFromConfig();

  const [universe, setUniverse] = useState<UniverseKey>(initialUniverse);
  const [factorWeights, setFactorWeights] =
    useState<FactorWeights>(initialWeights);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [state, formAction] = useActionState(
    runScreener,
    initialRunScreenerState,
  );
  const { setRail, closeRail } = useAppShellRail();

  const results = useMemo<ScreenerResult[]>(
    () => (initialRun ? [...initialRun.results] : []),
    [initialRun],
  );

  useEffect(() => {
    if (state.status === "error" && state.message !== null) {
      toast.error(state.message);
    }
  }, [state]);

  useEffect(() => {
    if (!selectedTicker) {
      return;
    }
    setRail({
      title: `${selectedTicker} preview`,
      body: <PromotePanel ticker={selectedTicker} />,
    });
  }, [selectedTicker, setRail]);

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
        <form action={formAction} className="flex flex-col gap-6">
          <input type="hidden" name="universe" value={universe} />
          {FACTOR_KEYS.map((key) => (
            <input
              key={`hidden-${key}`}
              type="hidden"
              name={`${WEIGHT_FIELD_PREFIX}${key}`}
              value={factorWeights[key].toString()}
            />
          ))}

          <div>
            <CapsLabel className="block mb-2">UNIVERSE</CapsLabel>
            <TooltipProvider delayDuration={150}>
              <Select
                value={universe}
                onValueChange={(next) => {
                  if (isUniverseKey(next)) {
                    setUniverse(next);
                  }
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {universeOptions.map((option) => {
                    const item = (
                      <SelectItem
                        key={option.key}
                        value={option.key}
                        disabled={option.isDisabled}
                      >
                        {option.label}
                      </SelectItem>
                    );
                    if (!option.isDisabled || !option.disabledReason) {
                      return item;
                    }
                    return (
                      <Tooltip key={option.key}>
                        <TooltipTrigger asChild>
                          <span className="block">{item}</span>
                        </TooltipTrigger>
                        <TooltipContent>
                          {option.disabledReason}
                        </TooltipContent>
                      </Tooltip>
                    );
                  })}
                </SelectContent>
              </Select>
            </TooltipProvider>
          </div>

          <div>
            <CapsLabel className="block mb-2">FACTORS</CapsLabel>
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
          </div>

          <SubmitButton isDisabled={false} />
        </form>
      </aside>

      <section className="flex-1 min-w-0 overflow-y-auto">
        <div className="px-6 py-6 flex flex-col gap-4">
          {loadError !== null ? (
            <div
              role="alert"
              className="rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
            >
              Failed to load screener run: {loadError}
            </div>
          ) : null}
          {initialRun === null ? (
            <div className="rounded-md border border-line bg-surface px-6 py-12 text-center text-sm text-fg-muted">
              Run a screener to see ranked tickers.
            </div>
          ) : (
            <DataTable<ScreenerResult>
              data={results}
              columns={resultColumns}
              getRowId={(row) => row.ticker}
              selectedRowId={selectedTicker ?? undefined}
              onRowClick={(row) => setSelectedTicker(row.ticker)}
            />
          )}
        </div>
      </section>
    </div>
  );
}

function isUniverseKey(value: string): value is UniverseKey {
  return value === "sp500" || value === "nasdaq100" || value === "watchlist";
}
