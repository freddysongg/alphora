import type { Metadata } from "next";
import type { ReactElement } from "react";

import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { Screener } from "./screener";

export const metadata: Metadata = {
  title: "Screener · Alphora",
};

export const dynamic = "force-dynamic";

type ScreenerRunResponse = components["schemas"]["ScreenerRunResponse"];

interface ScreenerPageSearchParams {
  run?: string | string[];
}

interface ScreenerPageProps {
  searchParams: Promise<ScreenerPageSearchParams>;
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function readRunId(params: ScreenerPageSearchParams): string | null {
  const raw = params.run;
  const candidate = Array.isArray(raw) ? raw[0] : raw;
  if (typeof candidate !== "string") {
    return null;
  }
  if (!UUID_PATTERN.test(candidate)) {
    return null;
  }
  return candidate;
}

interface LoadResult {
  run: ScreenerRunResponse | null;
  errorDetail: string | null;
}

async function loadScreenerRun(runId: string): Promise<LoadResult> {
  try {
    const { data } = await getServerApi().GET(
      "/api/screeners/runs/{screener_run_id}",
      {
        params: { path: { screener_run_id: runId } },
        cache: "force-cache",
        next: { tags: ["screener-run", `screener-run-${runId}`] },
      },
    );
    if (data === undefined) {
      return { run: null, errorDetail: null };
    }
    return { run: data, errorDetail: null };
  } catch (caught) {
    if (isApiError(caught)) {
      if (caught.status === 404) {
        console.warn(`screener run ${runId} not found`);
        return { run: null, errorDetail: null };
      }
      return { run: null, errorDetail: caught.detail };
    }
    throw caught;
  }
}

export default async function ScreenerPage(
  props: ScreenerPageProps,
): Promise<ReactElement> {
  const params = await props.searchParams;
  const runId = readRunId(params);
  const { run, errorDetail } = runId
    ? await loadScreenerRun(runId)
    : { run: null, errorDetail: null };

  return <Screener initialRun={run} loadError={errorDetail} />;
}
