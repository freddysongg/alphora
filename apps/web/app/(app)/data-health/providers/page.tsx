import type { Metadata } from "next";
import type { ReactElement } from "react";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { buildProviderOverview } from "@/lib/data-health/overview";
import type { DataSourceList } from "@/lib/data-health/types";
import { ProviderOverviewTable } from "./provider-overview";

export const metadata: Metadata = {
  title: "Data Health · Alphora",
};

export const dynamic = "force-dynamic";

type ProviderMatrixResponse = components["schemas"]["ProviderMatrix"];

const emptyMatrix: ProviderMatrixResponse = {
  providers: [],
  tools: [],
  cells: [],
};

const emptySources: DataSourceList = { sources: [] };

interface OverviewData {
  sources: DataSourceList;
  matrix: ProviderMatrixResponse;
  errorDetail: string | null;
}

async function loadOverviewData(): Promise<OverviewData> {
  try {
    const api = getServerApi();
    const [sourcesResult, matrixResult] = await Promise.all([
      api.GET("/api/data-sources", { cache: "no-store" }),
      api.GET("/api/data-health", { cache: "no-store" }),
    ]);
    return {
      sources: sourcesResult.data ?? emptySources,
      matrix: matrixResult.data ?? emptyMatrix,
      errorDetail: null,
    };
  } catch (caught) {
    if (isApiError(caught)) {
      return {
        sources: emptySources,
        matrix: emptyMatrix,
        errorDetail: caught.detail,
      };
    }
    throw caught;
  }
}

export default async function DataHealthPage(): Promise<ReactElement> {
  const { sources, matrix, errorDetail } = await loadOverviewData();
  const overview = buildProviderOverview(sources.sources, matrix);
  return (
    <>
      {errorDetail !== null ? (
        <div
          role="alert"
          className="mb-4 rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Failed to load data health: {errorDetail}
        </div>
      ) : null}
      {overview.rows.length > 0 ? (
        <ProviderOverviewTable overview={overview} />
      ) : (
        <div className="rounded-md border border-line bg-surface px-6 py-12 text-center text-sm text-fg-muted">
          No providers configured yet.
        </div>
      )}
    </>
  );
}
