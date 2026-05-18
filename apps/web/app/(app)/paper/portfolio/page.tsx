import type { Metadata } from "next";
import type { ReactElement } from "react";

import { CapsLabel } from "@/components/ui";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { centsToDollars } from "@/lib/format/cents";
import { NewOrderDialog } from "./new-order-dialog";
import { PositionsTable } from "./positions-table";

export const metadata: Metadata = {
  title: "Paper Portfolio · Alphora",
};

export const dynamic = "force-dynamic";

type PaperPortfolioSnapshot = components["schemas"]["PaperPortfolioSnapshot"];
type PaperPositionPublic = components["schemas"]["PaperPositionPublic"];

type SummaryToneKey = "neutral" | "positive" | "negative";

interface SummaryItem {
  label: string;
  value: string;
  tone: SummaryToneKey;
}

const toneClasses: Record<SummaryToneKey, string> = {
  neutral: "text-fg",
  positive: "text-accent-text",
  negative: "text-danger",
};

const FALLBACK = "—";

function toneFromCents(cents: number): SummaryToneKey {
  if (cents > 0) {
    return "positive";
  }
  if (cents < 0) {
    return "negative";
  }
  return "neutral";
}

function formatSignedCents(cents: number): string {
  const prefix = cents >= 0 ? "+" : "-";
  return `${prefix}${centsToDollars(Math.abs(cents))}`;
}

interface LoadResult {
  snapshot: PaperPortfolioSnapshot | null;
  errorDetail: string | null;
}

async function loadPortfolio(): Promise<LoadResult> {
  try {
    const { data } = await getServerApi().GET("/api/paper/portfolio", {
      cache: "force-cache",
      next: { tags: ["paper-portfolio"] },
    });
    if (data === undefined) {
      return { snapshot: null, errorDetail: null };
    }
    return { snapshot: data, errorDetail: null };
  } catch (caught) {
    if (isApiError(caught)) {
      return { snapshot: null, errorDetail: caught.detail };
    }
    throw caught;
  }
}

function buildSummary(
  snapshot: PaperPortfolioSnapshot | null,
): readonly SummaryItem[] {
  if (snapshot === null) {
    return [
      { label: "CASH", value: FALLBACK, tone: "neutral" },
      { label: "EQUITY", value: FALLBACK, tone: "neutral" },
      { label: "DAY P/L", value: FALLBACK, tone: "neutral" },
      { label: "ALL-TIME P/L", value: FALLBACK, tone: "neutral" },
      { label: "VS SPY", value: FALLBACK, tone: "neutral" },
    ];
  }
  const totalPlCents =
    snapshot.realized_pl_cents + snapshot.unrealized_pl_cents;
  return [
    {
      label: "CASH",
      value: centsToDollars(snapshot.cash_cents),
      tone: "neutral",
    },
    {
      label: "EQUITY",
      value: centsToDollars(snapshot.equity_cents),
      tone: "neutral",
    },
    { label: "DAY P/L", value: FALLBACK, tone: "neutral" },
    {
      label: "ALL-TIME P/L",
      value: formatSignedCents(totalPlCents),
      tone: toneFromCents(totalPlCents),
    },
    { label: "VS SPY", value: FALLBACK, tone: "neutral" },
  ];
}

export default async function PaperPortfolioPage(): Promise<ReactElement> {
  const { snapshot, errorDetail } = await loadPortfolio();
  const positions: readonly PaperPositionPublic[] =
    snapshot?.positions ?? [];
  const summaryItems = buildSummary(snapshot);
  const portfolioId = snapshot?.id ?? null;

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <header className="flex items-center justify-between pb-6">
        <CapsLabel as="h1">PAPER PORTFOLIO</CapsLabel>
        <NewOrderDialog portfolioId={portfolioId} />
      </header>

      {errorDetail !== null ? (
        <div
          role="alert"
          className="mb-4 rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Failed to load portfolio: {errorDetail}
        </div>
      ) : null}

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
        <PositionsTable rows={positions} />
      </section>
    </div>
  );
}
