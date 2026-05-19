import type { Metadata } from "next";
import type { ReactElement } from "react";
import Link from "next/link";
import type { Route } from "next";

import { Button, CapsLabel } from "@/components/ui";
import { HypothesisRow } from "@/components/research/hypothesis-row";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { HYPOTHESES_CACHE_TAG } from "./cache-tags";

export const metadata: Metadata = {
  title: "Hypotheses · Alphora",
};

export const dynamic = "force-dynamic";

type HypothesisPublic = components["schemas"]["HypothesisPublic"];
type HypothesisStateFilter =
  components["schemas"]["HypothesisStateFilter"];

const FILTER_VALUES = ["all", "proposed", "active"] as const;

function isStateFilter(value: string): value is HypothesisStateFilter {
  return (FILTER_VALUES as readonly string[]).includes(value);
}

interface FetchResult {
  items: HypothesisPublic[];
  nextCursor: string | null;
  errorDetail: string | null;
}

async function loadHypotheses(
  state: HypothesisStateFilter,
): Promise<FetchResult> {
  try {
    const { data } = await getServerApi().GET("/api/research/hypotheses", {
      params: { query: { state } },
      cache: "force-cache",
      next: { tags: [HYPOTHESES_CACHE_TAG] },
    });
    if (data === undefined) {
      return { items: [], nextCursor: null, errorDetail: null };
    }
    return {
      items: data.items,
      nextCursor: data.next_cursor ?? null,
      errorDetail: null,
    };
  } catch (caught) {
    if (isApiError(caught)) {
      return { items: [], nextCursor: null, errorDetail: caught.detail };
    }
    throw caught;
  }
}

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function HypothesesPage(
  props: PageProps,
): Promise<ReactElement> {
  const params = await props.searchParams;
  const rawState = typeof params.state === "string" ? params.state : "all";
  const state: HypothesisStateFilter = isStateFilter(rawState) ? rawState : "all";
  const { items, errorDetail } = await loadHypotheses(state);

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <header className="flex items-center justify-between pb-6">
        <CapsLabel as="h1" className="text-fg">
          HYPOTHESES
        </CapsLabel>
        <nav className="flex items-center gap-2" aria-label="Filter by state">
          {FILTER_VALUES.map((value) => (
            <Button
              key={value}
              asChild
              size="sm"
              variant={state === value ? "default" : "ghost"}
            >
              <Link
                href={
                  (value === "all"
                    ? "/research/hypotheses"
                    : `/research/hypotheses?state=${value}`) as Route
                }
              >
                {value.toUpperCase()}
              </Link>
            </Button>
          ))}
        </nav>
      </header>
      {errorDetail !== null ? (
        <div
          role="alert"
          className="mb-4 rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Failed to load hypotheses: {errorDetail}
        </div>
      ) : null}
      {items.length === 0 ? (
        <p className="px-3 py-4 text-xs text-fg-subtle">No hypotheses yet.</p>
      ) : (
        <ul>
          {items.map((hypothesis) => (
            <HypothesisRow key={hypothesis.id} hypothesis={hypothesis} />
          ))}
        </ul>
      )}
    </div>
  );
}
