"use client";

import { useMemo } from "react";
import type { ReactElement } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { CommandPalette } from "@/components/ui/command-palette";
import type { CommandItem } from "@/components/ui/command-palette";

const sampleTickers: ReadonlyArray<{ symbol: string }> = [
  { symbol: "AAPL" },
  { symbol: "NVDA" },
  { symbol: "MSFT" },
];

const sampleRuns: ReadonlyArray<{ id: string }> = [
  { id: "sb-aLPQ00ucncCYFzzZ0qiNoL" },
  { id: "sb-92mc0ApfxxV1u2H1n44iiZ" },
];

export function CommandPaletteMount(): ReactElement {
  const router = useRouter();

  const items = useMemo<CommandItem[]>(() => {
    const tickerItems: CommandItem[] = sampleTickers.map((ticker) => ({
      id: `ticker-${ticker.symbol}`,
      label: ticker.symbol,
      hint: "Company",
      section: "tickers",
      onSelect: () => router.push(`/companies/${ticker.symbol}` as Route),
    }));
    const runItems: CommandItem[] = sampleRuns.map((run) => ({
      id: `run-${run.id}`,
      label: run.id,
      hint: "Run",
      section: "runs",
      onSelect: () => router.push(`/research/runs/${run.id}` as Route),
    }));
    const reportItems: CommandItem[] = [
      {
        id: "report-latest",
        label: "Latest research report",
        hint: "Report",
        section: "reports",
        onSelect: () => router.push("/research/reports" as Route),
      },
    ];
    const settingItems: CommandItem[] = [
      {
        id: "settings-api-keys",
        label: "API Keys",
        hint: "Settings",
        section: "settings",
        onSelect: () => router.push("/settings/api-keys" as Route),
      },
    ];
    return [...tickerItems, ...runItems, ...reportItems, ...settingItems];
  }, [router]);

  return <CommandPalette items={items} />;
}
