import type { Metadata } from "next";
import type { ReactElement } from "react";
import type { Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "@phosphor-icons/react/dist/ssr";

import { Button, HexPill } from "@/components/ui";
import {
  HypothesisBeliefExplainer,
  type HypothesisBeliefBundle,
} from "@/components/research/hypothesis-belief-explainer";
import {
  HypothesisLifecycleCard,
  type HypothesisLifecycleBundle,
} from "@/components/research/hypothesis-lifecycle-card";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";

export const metadata: Metadata = {
  title: "Run Hypotheses · Alphora",
};

export const dynamic = "force-dynamic";

type ResearchRunDetail = components["schemas"]["ResearchRunDetail"];
type HypothesisPublic = components["schemas"]["HypothesisPublic"];
type BeliefRecomputationPublic =
  components["schemas"]["BeliefRecomputationPublic"];
type HypothesisLifecycleResponse =
  components["schemas"]["HypothesisLifecycleResponse"];

interface RunHypothesesPageProps {
  params: Promise<{ id: string }>;
}

const NOT_FOUND_STATUS = 404;
const HYPOTHESIS_FETCH_LIMIT = 100;

async function loadRunDetail(runId: string): Promise<ResearchRunDetail | null> {
  try {
    const { data } = await getServerApi().GET("/api/research-runs/{run_id}", {
      params: { path: { run_id: runId } },
      cache: "no-store",
    });
    return data ?? null;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

async function loadHypothesesForRun(
  runId: string,
): Promise<readonly HypothesisPublic[]> {
  try {
    const { data } = await getServerApi().GET("/api/research/hypotheses", {
      params: { query: { run_id: runId, limit: HYPOTHESIS_FETCH_LIMIT } },
      cache: "no-store",
    });
    return data?.items ?? [];
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return [];
    }
    throw caught;
  }
}

async function loadLatestBelief(
  hypothesisId: string,
): Promise<BeliefRecomputationPublic | null> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research/hypotheses/{hypothesis_id}/belief",
      {
        params: { path: { hypothesis_id: hypothesisId } },
        cache: "no-store",
      },
    );
    return data?.latest ?? null;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

async function loadHypothesisLifecycle(
  hypothesisId: string,
): Promise<HypothesisLifecycleResponse | null> {
  try {
    const { data } = await getServerApi().GET(
      "/api/research/hypotheses/{hypothesis_id}/lifecycle",
      {
        params: { path: { hypothesis_id: hypothesisId } },
        cache: "no-store",
      },
    );
    return data ?? null;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

async function loadBundles(hypotheses: readonly HypothesisPublic[]): Promise<{
  beliefBundles: readonly HypothesisBeliefBundle[];
  lifecycleBundles: readonly HypothesisLifecycleBundle[];
}> {
  const beliefBundles = await Promise.all(
    hypotheses.map(async (hypothesis) => {
      const latest = await loadLatestBelief(hypothesis.id);
      return { hypothesis, latest };
    }),
  );
  const lifecycleBundles = await Promise.all(
    hypotheses.map(async (hypothesis) => {
      const lifecycle = await loadHypothesisLifecycle(hypothesis.id);
      return { hypothesis, lifecycle };
    }),
  );
  return { beliefBundles, lifecycleBundles };
}

export default async function RunHypothesesPage(
  props: RunHypothesesPageProps,
): Promise<ReactElement> {
  const { id } = await props.params;
  const detail = await loadRunDetail(id);
  if (detail === null) {
    notFound();
  }
  if (detail.strategy !== "funnel_research") {
    notFound();
  }

  const hypotheses = await loadHypothesesForRun(id);
  const { beliefBundles, lifecycleBundles } = await loadBundles(hypotheses);
  const runHref = `/research/runs/${id}` as Route;

  return (
    <div className="max-w-[1100px] mx-auto">
      <header className="sticky top-0 z-10 bg-canvas border-b border-line">
        <div className="flex items-center gap-4 px-6 py-4">
          <Button asChild size="sm" variant="ghost" aria-label="Back to run">
            <Link href={runHref}>
              <ArrowLeft size={12} weight="regular" />
            </Link>
          </Button>
          <span className="text-2xl font-mono tabular-nums text-fg">
            HYPOTHESES
          </span>
          <HexPill value={detail.id} />
        </div>
      </header>

      <div className="px-6 pt-4 pb-12 flex flex-col gap-6">
        {hypotheses.length === 0 ? (
          <p className="text-sm text-fg-muted">
            No hypotheses recorded for this run yet.
          </p>
        ) : (
          <>
            <HypothesisLifecycleCard bundles={lifecycleBundles} />
            <HypothesisBeliefExplainer bundles={beliefBundles} />
          </>
        )}
      </div>
    </div>
  );
}
