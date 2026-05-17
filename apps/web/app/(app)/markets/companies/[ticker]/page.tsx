import type { Metadata } from "next";
import type { ReactElement } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CodeBlock,
  Sparkline,
} from "@/components/ui";
import { sampleTickers } from "@/lib/fixtures/tickers";
import type { TickerRow } from "@/lib/fixtures/tickers";
import { FactorHistoryChart } from "./factor-history-chart";
import {
  HistoricalRunsTable,
  LinkedPositionsTable,
} from "./dossier-tables";

export const metadata: Metadata = {
  title: "Company Dossier · Alphora",
};

const FALLBACK_TICKER: TickerRow = {
  ticker: "AAPL",
  name: "Apple Inc.",
  sector: "Technology",
  price: 212.45,
  dayPct: 1.42,
  score: 0.82,
  quality: 0.91,
  valuation: 0.62,
  momentum: 0.78,
  volatility: 0.21,
  sentiment: 0.74,
  priceHistory: [
    168, 170, 172, 169, 174, 178, 181, 179, 182, 185, 188, 187, 190, 193, 191,
    195, 198, 196, 199, 202, 204, 207, 210, 212,
  ],
};

function formatPrice(value: number): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

interface DossierPageProps {
  params: Promise<{ ticker: string }>;
}

const noteSample = `# AAPL notes

- Services momentum: 28% of revenue, margin > 70%
- Watch: China demand inflection on FQ3 print
- Hedge: pair with 0.4x QQQ short for sector beta`;

export default async function CompanyDossierPage(
  props: DossierPageProps,
): Promise<ReactElement> {
  const { ticker } = await props.params;
  const matched = sampleTickers.find(
    (row) => row.ticker.toLowerCase() === ticker.toLowerCase(),
  );
  const company = matched ?? { ...FALLBACK_TICKER, ticker: ticker.toUpperCase() };
  const dayPctClass = company.dayPct >= 0 ? "text-accent-text" : "text-danger";

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <section className="border-b border-line pb-6">
        <div className="flex items-end gap-6">
          <h1 className="text-3xl tracking-[-0.03em] font-semibold text-fg">
            {company.ticker}
          </h1>
          <div className="flex flex-col gap-1">
            <span className="font-mono tabular-nums text-base text-fg">
              {formatPrice(company.price)}
            </span>
            <span className={`font-mono text-xs ${dayPctClass}`}>
              {company.dayPct >= 0 ? "+" : ""}
              {company.dayPct.toFixed(2)}%
            </span>
          </div>
          <span className="text-xs text-fg-muted ml-4">{company.name}</span>
        </div>
        <div className="mt-4">
          <Sparkline
            data={[...company.priceHistory]}
            width="100%"
            height={60}
          />
        </div>
      </section>

      <section className="grid grid-cols-2 gap-6 mt-8">
        <Card>
          <CardHeader>
            <CardTitle>HISTORICAL RUNS</CardTitle>
          </CardHeader>
          <CardContent>
            <HistoricalRunsTable />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>FACTOR HISTORY</CardTitle>
          </CardHeader>
          <CardContent>
            <FactorHistoryChart />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>LINKED PAPER POSITIONS</CardTitle>
          </CardHeader>
          <CardContent>
            <LinkedPositionsTable />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>NOTES</CardTitle>
          </CardHeader>
          <CardContent>
            <CodeBlock lang="markdown">{noteSample}</CodeBlock>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
