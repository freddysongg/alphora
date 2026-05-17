import type { Metadata } from "next";
import type { ReactElement } from "react";
import { CapsLabel } from "@/components/ui";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { ProviderMatrix } from "./provider-matrix";

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

interface FetchResult {
  matrix: ProviderMatrixResponse;
  errorDetail: string | null;
}

async function loadProviderMatrix(): Promise<FetchResult> {
  try {
    const { data } = await getServerApi().GET("/api/data-health", {
      cache: "force-cache",
      next: { tags: ["data-health"] },
    });
    if (data === undefined) {
      return { matrix: emptyMatrix, errorDetail: null };
    }
    return { matrix: data, errorDetail: null };
  } catch (caught) {
    if (isApiError(caught)) {
      return { matrix: emptyMatrix, errorDetail: caught.detail };
    }
    throw caught;
  }
}

export default async function DataHealthPage(): Promise<ReactElement> {
  const { matrix, errorDetail } = await loadProviderMatrix();
  const hasEntries = matrix.providers.length > 0 && matrix.tools.length > 0;
  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <header className="pb-6">
        <CapsLabel as="h1">DATA HEALTH</CapsLabel>
      </header>
      {errorDetail !== null ? (
        <div
          role="alert"
          className="mb-4 rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Failed to load data health: {errorDetail}
        </div>
      ) : null}
      {hasEntries ? (
        <ProviderMatrix matrix={matrix} />
      ) : (
        <div className="rounded-md border border-line bg-surface px-6 py-12 text-center text-sm text-fg-muted">
          No data health entries yet.
        </div>
      )}
    </div>
  );
}
