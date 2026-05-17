import type { Metadata } from "next";
import type { ReactElement } from "react";
import { CapsLabel } from "@/components/ui";
import {
  samplePortfolioSummary,
  samplePositions,
} from "@/lib/fixtures/portfolio";
import { NewOrderDialog } from "./new-order-dialog";
import { PositionsTable } from "./positions-table";

export const metadata: Metadata = {
  title: "Paper Portfolio · Alphora",
};

type SummaryToneKey = "neutral" | "positive" | "negative";

interface SummaryItem {
  label: string;
  value: string;
  tone: SummaryToneKey;
}

function formatMoney(value: number): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatSignedMoney(value: number): string {
  const prefix = value >= 0 ? "+" : "";
  return `${prefix}${formatMoney(value)}`;
}

function formatSignedPct(value: number): string {
  const prefix = value >= 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)}%`;
}

function tone(value: number): SummaryToneKey {
  if (value > 0) {
    return "positive";
  }
  if (value < 0) {
    return "negative";
  }
  return "neutral";
}

const toneClasses: Record<SummaryToneKey, string> = {
  neutral: "text-fg",
  positive: "text-accent-text",
  negative: "text-danger",
};

export default function PaperPortfolioPage(): ReactElement {
  const summaryItems: readonly SummaryItem[] = [
    { label: "CASH", value: formatMoney(samplePortfolioSummary.cash), tone: "neutral" },
    {
      label: "EQUITY",
      value: formatMoney(samplePortfolioSummary.equity),
      tone: "neutral",
    },
    {
      label: "DAY P/L",
      value: formatSignedMoney(samplePortfolioSummary.dayPl),
      tone: tone(samplePortfolioSummary.dayPl),
    },
    {
      label: "ALL-TIME P/L",
      value: formatSignedMoney(samplePortfolioSummary.allTimePl),
      tone: tone(samplePortfolioSummary.allTimePl),
    },
    {
      label: "VS SPY",
      value: formatSignedPct(samplePortfolioSummary.vsSpyPct),
      tone: tone(samplePortfolioSummary.vsSpyPct),
    },
  ];

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <header className="flex items-center justify-between pb-6">
        <CapsLabel as="h1">PAPER PORTFOLIO</CapsLabel>
        <NewOrderDialog />
      </header>

      <section className="flex border-t border-b border-line">
        {summaryItems.map((item, index) => (
          <div
            key={item.label}
            className={`flex-1 px-6 py-4 flex flex-col gap-1 ${
              index < summaryItems.length - 1 ? "border-r border-line" : ""
            }`}
          >
            <CapsLabel>{item.label}</CapsLabel>
            <span
              className={`font-mono tabular-nums text-base ${toneClasses[item.tone]}`}
            >
              {item.value}
            </span>
          </div>
        ))}
      </section>

      <section className="mt-8">
        <PositionsTable rows={samplePositions} />
      </section>
    </div>
  );
}
