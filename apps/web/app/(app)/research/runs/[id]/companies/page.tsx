import type { Metadata } from "next";
import type { ReactElement } from "react";
import type { Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, CaretRight } from "@phosphor-icons/react/dist/ssr";

import { Button, CapsLabel, HexPill, StatusPill } from "@/components/ui";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { getMacroBrief } from "../actions";
import { cn } from "@/lib/cn";

export const metadata: Metadata = {
  title: "Run Companies · Alphora",
};

export const dynamic = "force-dynamic";

type ResearchRunDetail = components["schemas"]["ResearchRunDetail"];
type SectorBriefPublic = components["schemas"]["SectorBriefPublic"];
type SectorCompanyIdea = components["schemas"]["SectorCompanyIdea"];

interface RunCompaniesPageProps {
  params: Promise<{ id: string }>;
}

interface CompanyEntry {
  sectorEntityId: string;
  sectorName: string;
  company: SectorCompanyIdea;
}

const NOT_FOUND_STATUS = 404;

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

function flattenCompanies(
  sectors: readonly SectorBriefPublic[],
): CompanyEntry[] {
  const entries: CompanyEntry[] = [];
  for (const sector of sectors) {
    for (const company of sector.brief.companies) {
      entries.push({
        sectorEntityId: sector.brief.sector_entity_id,
        sectorName: sector.brief.sector_name,
        company,
      });
    }
  }
  return entries;
}

export default async function RunCompaniesPage(
  props: RunCompaniesPageProps,
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
  const entries = flattenCompanies(macroBrief?.sector_briefs ?? []);
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
            COMPANIES
          </span>
          <HexPill value={detail.id} />
        </div>
      </header>

      <div className="px-6 pt-4 pb-12">
        {entries.length === 0 ? (
          <p className="text-sm text-fg-muted">
            No company theses produced for this run yet.
          </p>
        ) : (
          <ul className="flex flex-col">
            {entries.map((entry) => (
              <CompanyRow
                key={`${entry.sectorEntityId}-${entry.company.name}`}
                runId={id}
                entry={entry}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

interface CompanyRowProps {
  runId: string;
  entry: CompanyEntry;
}

function CompanyRow(props: CompanyRowProps): ReactElement {
  const { runId, entry } = props;
  const companyEntityId = entry.company.company_entity_id;
  const href =
    companyEntityId !== null && companyEntityId !== undefined
      ? (`/research/runs/${runId}/companies/${companyEntityId}` as Route)
      : null;

  const label = entry.company.ticker
    ? `${entry.company.ticker} · ${entry.company.name}`
    : entry.company.name;
  const summary = `${entry.sectorName} · ${entry.company.direction.toUpperCase()} · conviction ${entry.company.conviction.toFixed(2)}`;

  const inner = (
    <div className="flex items-center gap-4 py-4 border-t border-line/60">
      <div className="w-72 shrink-0">
        <CapsLabel className="text-fg">{label}</CapsLabel>
      </div>
      <StatusPill status="succeeded" />
      <span className="text-sm text-fg-muted truncate min-w-0 flex-1">
        {summary}
      </span>
      {href !== null ? (
        <CaretRight
          size={14}
          weight="regular"
          className="text-fg-subtle group-hover:text-fg shrink-0"
        />
      ) : null}
    </div>
  );

  if (href === null) {
    return <li>{inner}</li>;
  }
  return (
    <li>
      <Link
        href={href}
        className={cn(
          "group block px-3 -mx-3 rounded-md transition-colors duration-150",
          "hover:bg-surface-2",
        )}
      >
        {inner}
      </Link>
    </li>
  );
}
