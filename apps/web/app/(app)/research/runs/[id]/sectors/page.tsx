import type { Metadata } from "next";
import type { ReactElement } from "react";
import type { Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, CaretRight } from "@phosphor-icons/react/dist/ssr";

import { Button, CapsLabel, HexPill, StatusDot } from "@/components/ui";
import type { StatusKind } from "@/components/ui";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { getMacroBrief } from "../actions";
import { cn } from "@/lib/cn";

export const metadata: Metadata = {
  title: "Run Sectors · Alphora",
};

export const dynamic = "force-dynamic";

type ResearchRunDetail = components["schemas"]["ResearchRunDetail"];
type SectorBriefPublic = components["schemas"]["SectorBriefPublic"];
type VerifierStatus = components["schemas"]["VerifierStatus"];

interface RunSectorsPageProps {
  params: Promise<{ id: string }>;
}

const NOT_FOUND_STATUS = 404;

const verifierStatusToDot: Record<VerifierStatus, StatusKind> = {
  verified: "succeeded",
  quote_unverified: "stale",
};

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

function sectorSummary(sector: SectorBriefPublic): string {
  const themeCount = sector.brief.themes.length;
  const companyCount = sector.brief.companies.length;
  return `${themeCount} themes · ${companyCount} companies · ${sector.brief.direction.toUpperCase()}`;
}

export default async function RunSectorsPage(
  props: RunSectorsPageProps,
): Promise<ReactElement> {
  const { id } = await props.params;
  const detail = await loadRunDetail(id);
  if (detail === null) {
    notFound();
  }
  if (detail.strategy !== "funnel_research") {
    notFound();
  }

  const macroBrief = await getMacroBrief(id);
  const sectors = macroBrief?.sector_briefs ?? [];
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
            SECTORS
          </span>
          <HexPill value={detail.id} />
        </div>
      </header>

      <div className="px-6 pt-4 pb-12">
        {sectors.length === 0 ? (
          <p className="text-sm text-fg-muted">
            No sector briefs produced for this run yet.
          </p>
        ) : (
          <ul className="flex flex-col">
            {sectors.map((sector) => (
              <SectorRow
                key={sector.brief.sector_entity_id}
                runId={id}
                sector={sector}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

interface SectorRowProps {
  runId: string;
  sector: SectorBriefPublic;
}

function SectorRow(props: SectorRowProps): ReactElement {
  const { runId, sector } = props;
  const href =
    `/research/runs/${runId}/sectors/${sector.brief.sector_entity_id}` as Route;
  return (
    <li>
      <Link
        href={href}
        className={cn(
          "group block px-3 -mx-3 rounded-md transition-colors duration-150",
          "hover:bg-surface-2",
        )}
      >
        <div className="flex items-center gap-4 py-4 border-t border-line/60">
          <div className="w-56 shrink-0">
            <CapsLabel className="text-fg">
              {sector.brief.sector_name}
            </CapsLabel>
          </div>
          <StatusDot
            status={verifierStatusToDot[sector.brief.verifier_status]}
          />
          <span className="text-sm text-fg-muted truncate min-w-0 flex-1">
            {sectorSummary(sector)}
          </span>
          <CaretRight
            size={14}
            weight="regular"
            className="text-fg-subtle group-hover:text-fg shrink-0"
          />
        </div>
      </Link>
    </li>
  );
}
