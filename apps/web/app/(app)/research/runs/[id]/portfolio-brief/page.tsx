import type { Metadata } from "next";
import type { ReactElement } from "react";
import type { Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "@phosphor-icons/react/dist/ssr";

import { Button, HexPill } from "@/components/ui";
import { PortfolioBriefDetail } from "@/components/research/portfolio-brief-detail";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { getPortfolioBrief } from "../actions";

export const metadata: Metadata = {
  title: "Portfolio Brief · Alphora",
};

export const dynamic = "force-dynamic";

type ResearchRunDetail = components["schemas"]["ResearchRunDetail"];

interface PortfolioBriefPageProps {
  params: Promise<{ id: string }>;
}

const NOT_FOUND_STATUS = 404;

async function loadRunDetail(
  runId: string,
): Promise<ResearchRunDetail | null> {
  try {
    const { data } = await getServerApi().GET("/api/research-runs/{run_id}", {
      params: { path: { run_id: runId } },
      cache: "force-cache",
      next: { tags: ["research-runs", `research-run-${runId}`] },
    });
    if (data === undefined) {
      return null;
    }
    return data;
  } catch (caught) {
    if (isApiError(caught) && caught.status === NOT_FOUND_STATUS) {
      return null;
    }
    throw caught;
  }
}

export default async function PortfolioBriefPage(
  props: PortfolioBriefPageProps,
): Promise<ReactElement> {
  const { id } = await props.params;
  const detail = await loadRunDetail(id);
  if (detail === null) {
    notFound();
  }
  if (detail.strategy !== "funnel_research") {
    notFound();
  }

  const portfolioBrief = await getPortfolioBrief(id);
  const runHref = `/research/runs/${id}` as Route;

  return (
    <div className="max-w-[1400px] mx-auto">
      <header className="sticky top-0 z-10 bg-canvas border-b border-line">
        <div className="flex items-center gap-4 px-6 py-4">
          <Button asChild size="sm" variant="ghost" aria-label="Back to run">
            <Link href={runHref}>
              <ArrowLeft size={12} weight="regular" />
            </Link>
          </Button>
          <span className="text-2xl font-mono tabular-nums text-fg">
            PORTFOLIO BRIEF
          </span>
          <HexPill value={detail.id} />
        </div>
      </header>

      <div className="px-6 pt-4 pb-12">
        {portfolioBrief !== null ? (
          <PortfolioBriefDetail data={portfolioBrief} />
        ) : detail.status === "failed" || detail.status === "cancelled" ? (
          <p className="text-sm text-fg-muted">
            Portfolio brief was not produced because the run was {detail.status}.
          </p>
        ) : (
          <p className="text-sm text-fg-muted">Portfolio brief is generating…</p>
        )}
      </div>
    </div>
  );
}
