import type { Metadata } from "next";
import type { ReactElement } from "react";
import { notFound } from "next/navigation";

import { HexPill } from "@/components/ui";
import { RunBreadcrumbs } from "@/components/research/run-breadcrumbs";
import { SectorBriefCard } from "@/components/research/sector-brief-card";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { getSectorBrief } from "../../actions";

export const metadata: Metadata = {
  title: "Sector Brief · Alphora",
};

export const dynamic = "force-dynamic";

type ResearchRunDetail = components["schemas"]["ResearchRunDetail"];

interface SectorBriefPageProps {
  params: Promise<{ id: string; sectorEntityId: string }>;
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

export default async function SectorBriefPage(
  props: SectorBriefPageProps,
): Promise<ReactElement> {
  const { id, sectorEntityId } = await props.params;
  const detail = await loadRunDetail(id);
  if (detail === null) {
    notFound();
  }
  if (detail.strategy !== "funnel_research") {
    notFound();
  }

  const sectorBrief = await getSectorBrief(id, sectorEntityId);

  return (
    <div className="max-w-[1400px] mx-auto">
      <header className="sticky top-0 z-10 bg-canvas border-b border-line">
        <div className="flex flex-col gap-2 px-6 py-4">
          <RunBreadcrumbs runId={id} variant="sector" />
          <div className="flex items-center gap-4">
            <span className="text-2xl font-mono tabular-nums text-fg">
              SECTOR BRIEF
            </span>
            <HexPill value={sectorEntityId} />
          </div>
        </div>
      </header>

      <div className="px-6 pt-4 pb-12">
        {sectorBrief !== null ? (
          <SectorBriefCard sectorBrief={sectorBrief} />
        ) : detail.status === "failed" || detail.status === "cancelled" ? (
          <p className="text-sm text-fg-muted">
            Sector brief was not produced because the run was {detail.status}.
          </p>
        ) : (
          <p className="text-sm text-fg-muted">Sector brief is generating…</p>
        )}
      </div>
    </div>
  );
}
