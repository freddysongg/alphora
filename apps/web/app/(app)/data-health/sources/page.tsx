import type { Metadata } from "next";
import type { ReactElement } from "react";
import { getServerApi, isApiError } from "@/lib/api";
import type { DataSourceList } from "@/lib/data-health/types";
import { SourcesWorkspace } from "./sources-workspace";

export const metadata: Metadata = {
  title: "Data Sources · Alphora",
};

export const dynamic = "force-dynamic";

interface FetchResult {
  readonly list: DataSourceList;
  readonly errorDetail: string | null;
}

const EMPTY_LIST: DataSourceList = { sources: [] };

async function loadDataSources(): Promise<FetchResult> {
  try {
    const { data } = await getServerApi().GET("/api/data-sources", {
      cache: "no-store",
    });
    if (data === undefined) {
      return { list: EMPTY_LIST, errorDetail: null };
    }
    return { list: data, errorDetail: null };
  } catch (caught) {
    if (isApiError(caught)) {
      return { list: EMPTY_LIST, errorDetail: caught.detail };
    }
    throw caught;
  }
}

export default async function SourcesPage(): Promise<ReactElement> {
  const { list, errorDetail } = await loadDataSources();
  return (
    <>
      {errorDetail !== null ? (
        <div
          role="alert"
          className="mb-4 rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Failed to load data sources: {errorDetail}
        </div>
      ) : null}
      <SourcesWorkspace initialSources={list.sources} />
    </>
  );
}
