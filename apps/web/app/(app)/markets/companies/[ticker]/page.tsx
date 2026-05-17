import type { Metadata } from "next";
import type { ReactElement } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { FactorHistoryChart } from "./factor-history-chart";
import {
  HistoricalRunsTable,
  LinkedPositionsTable,
} from "./dossier-tables";

export const metadata: Metadata = {
  title: "Company Dossier · Alphora",
};

export const dynamic = "force-dynamic";

type ResearchRunSummary = components["schemas"]["ResearchRunSummary"];
type PaperPortfolioSnapshot = components["schemas"]["PaperPortfolioSnapshot"];
type PaperPositionPublic = components["schemas"]["PaperPositionPublic"];

const DASH = "—";
const HISTORICAL_RUN_LIMIT = 50;

interface DossierPageProps {
  params: Promise<{ ticker: string }>;
}

interface DossierLoadResult {
  historicalRuns: readonly ResearchRunSummary[];
  linkedPositions: readonly PaperPositionPublic[];
  portfolioName: string;
  errorDetail: string | null;
}

async function loadHistoricalRuns(
  ticker: string,
): Promise<ResearchRunSummary[]> {
  const { data } = await getServerApi().GET("/api/research-runs", {
    params: {
      query: { ticker, limit: HISTORICAL_RUN_LIMIT },
    },
    cache: "force-cache",
    next: { tags: ["research-runs", `research-runs-ticker-${ticker}`] },
  });
  if (data === undefined || !Array.isArray(data)) {
    return [];
  }
  return data;
}

async function loadPaperPortfolio(): Promise<PaperPortfolioSnapshot | null> {
  const { data } = await getServerApi().GET("/api/paper/portfolio", {
    cache: "force-cache",
    next: { tags: ["paper-portfolio"] },
  });
  if (data === undefined) {
    return null;
  }
  return data;
}

async function loadDossier(ticker: string): Promise<DossierLoadResult> {
  try {
    const [historicalRuns, portfolio] = await Promise.all([
      loadHistoricalRuns(ticker),
      loadPaperPortfolio(),
    ]);
    const positions = portfolio?.positions ?? [];
    const linkedPositions = positions.filter(
      (position) =>
        position.ticker === ticker && position.closed_at === null,
    );
    return {
      historicalRuns,
      linkedPositions,
      portfolioName: portfolio?.name ?? DASH,
      errorDetail: null,
    };
  } catch (caught) {
    if (isApiError(caught)) {
      return {
        historicalRuns: [],
        linkedPositions: [],
        portfolioName: DASH,
        errorDetail: caught.detail,
      };
    }
    throw caught;
  }
}

export default async function CompanyDossierPage(
  props: DossierPageProps,
): Promise<ReactElement> {
  const { ticker } = await props.params;
  const upperTicker = ticker.toUpperCase();
  const { historicalRuns, linkedPositions, portfolioName, errorDetail } =
    await loadDossier(upperTicker);

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <section className="border-b border-line pb-6">
        <div className="flex items-end gap-6">
          <h1 className="text-3xl tracking-[-0.03em] font-semibold text-fg">
            {upperTicker}
          </h1>
          <span className="text-xs text-fg-muted ml-4">{DASH}</span>
        </div>
      </section>

      {errorDetail !== null ? (
        <div
          role="alert"
          className="mt-6 rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Failed to load dossier: {errorDetail}
        </div>
      ) : null}

      <section className="grid grid-cols-2 gap-6 mt-8">
        <Card>
          <CardHeader>
            <CardTitle>HISTORICAL RUNS</CardTitle>
          </CardHeader>
          <CardContent>
            <HistoricalRunsTable runs={historicalRuns} />
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
            <LinkedPositionsTable
              positions={linkedPositions}
              portfolioName={portfolioName}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>NOTES</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-32 w-full flex items-center justify-center text-xs text-fg-muted">
              Notes not yet supported.
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
