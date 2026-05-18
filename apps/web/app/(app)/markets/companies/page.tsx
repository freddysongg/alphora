import type { Metadata } from "next";
import type { ReactElement } from "react";
import { CapsLabel } from "@/components/ui";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { dedupeTickers } from "@/lib/companies/dedupe-tickers";
import { CompaniesTable } from "./companies-table";
import type { CompanyRow } from "./companies-table";

export const metadata: Metadata = {
  title: "Companies · Alphora",
};

export const dynamic = "force-dynamic";

type ResearchRunSummary = components["schemas"]["ResearchRunSummary"];

const RESEARCH_RUN_LIMIT = 200;

interface LoadResult {
  rows: readonly CompanyRow[];
  errorDetail: string | null;
}

async function loadCompanyRows(): Promise<LoadResult> {
  try {
    const { data } = await getServerApi().GET("/api/research-runs", {
      params: { query: { limit: RESEARCH_RUN_LIMIT } },
      cache: "force-cache",
      next: { tags: ["companies", "research-runs"] },
    });
    if (data === undefined || !Array.isArray(data)) {
      return { rows: [], errorDetail: null };
    }
    const runs: ResearchRunSummary[] = data;
    const tickers = dedupeTickers(runs);
    const rows: CompanyRow[] = tickers.map((ticker) => ({ ticker }));
    return { rows, errorDetail: null };
  } catch (caught) {
    if (isApiError(caught)) {
      return { rows: [], errorDetail: caught.detail };
    }
    throw caught;
  }
}

export default async function CompaniesIndexPage(): Promise<ReactElement> {
  const { rows, errorDetail } = await loadCompanyRows();
  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <header className="pb-6">
        <CapsLabel as="h1">COMPANIES</CapsLabel>
      </header>
      {errorDetail !== null ? (
        <div
          role="alert"
          className="mb-4 rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Failed to load companies: {errorDetail}
        </div>
      ) : null}
      <CompaniesTable rows={rows} />
    </div>
  );
}
