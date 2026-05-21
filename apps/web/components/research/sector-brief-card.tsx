"use client";

import { useMemo, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import type { Route } from "next";
import Link from "next/link";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CapsLabel,
} from "@/components/ui";
import { useEvidenceDisclosure } from "@/components/research/evidence-disclosure";
import type { components } from "@/lib/api";

type SectorBriefPublic = components["schemas"]["SectorBriefPublic"];
type ChunkLookup = components["schemas"]["ChunkLookup"];
type CitedClaim = components["schemas"]["CitedClaim"];
type SectorCompanyIdea = components["schemas"]["SectorCompanyIdea"];
type Theme = components["schemas"]["Theme"];
type WatchItem = components["schemas"]["WatchItem"];

const DIRECTION_TONE: Record<string, string> = {
  overweight: "text-success",
  underweight: "text-danger",
  neutral: "text-fg-subtle",
};

const CHUNK_PREVIEW_LENGTH = 200;

export interface SectorBriefCardProps {
  sectorBrief: SectorBriefPublic;
  runId?: string;
}

export function SectorBriefCard(props: SectorBriefCardProps): ReactElement {
  const { sectorBrief, runId } = props;
  const { brief, judge, chunks } = sectorBrief;
  const directionTone = DIRECTION_TONE[brief.direction] ?? "text-fg";
  const convictionPct = Math.round(
    Math.max(0, Math.min(1, brief.confidence)) * 100,
  );

  const chunkById = useMemo(() => {
    const map = new Map<string, ChunkLookup>();
    for (const chunk of chunks) {
      map.set(chunk.chunk_id, chunk);
    }
    return map;
  }, [chunks]);

  const sectorTitle =
    runId !== undefined ? (
      <Link
        href={
          `/research/runs/${runId}/sectors/${brief.sector_entity_id}` as Route
        }
        className="text-fg hover:text-accent-text hover:underline transition-colors duration-150"
        data-testid="sector-brief-detail-link"
      >
        {brief.sector_name}
      </Link>
    ) : (
      brief.sector_name
    );

  return (
    <Card className="p-0" data-testid="sector-brief-card">
      <CardHeader className="flex flex-row items-center justify-between gap-4 px-6 pt-6 pb-5">
        <CardTitle className="text-base normal-case tracking-normal text-fg">
          {sectorTitle}
        </CardTitle>
        <CapsLabel className={directionTone}>{brief.direction}</CapsLabel>
      </CardHeader>

      <CardContent className="flex flex-col">
        <Band>
          <BandBody className="flex flex-col gap-4">
            <div className="flex items-center gap-3">
              <CapsLabel className="text-fg-subtle w-24 shrink-0">
                CONVICTION
              </CapsLabel>
              <div
                role="progressbar"
                aria-label="conviction"
                aria-valuenow={convictionPct}
                aria-valuemin={0}
                aria-valuemax={100}
                className="h-1 flex-1 bg-surface-2 rounded-full overflow-hidden"
              >
                <div
                  className="h-full bg-accent"
                  style={{ width: `${convictionPct}%` }}
                />
              </div>
              <span className="font-mono text-xs text-fg tabular-nums w-10 text-right">
                {convictionPct}%
              </span>
            </div>
            <div className="flex items-center gap-3">
              <CapsLabel className="text-fg-subtle w-24 shrink-0">
                JUDGE
              </CapsLabel>
              <span className="font-mono text-xs text-fg">{judge.status}</span>
            </div>
          </BandBody>
        </Band>

        {brief.themes.length > 0 ? (
          <Band>
            <BandHeader title="THEMES" count={brief.themes.length} />
            <BandBody>
              <ul
                className="flex flex-col gap-3"
                data-testid="sector-themes"
              >
                {brief.themes.map((theme) => (
                  <SectorThemeRow
                    key={theme.name}
                    theme={theme}
                    runId={runId}
                  />
                ))}
              </ul>
            </BandBody>
          </Band>
        ) : null}

        {brief.companies.length > 0 ? (
          <Band>
            <BandHeader
              title="COMPANIES"
              count={brief.companies.length}
            />
            <BandBody>
              <ul
                className="flex flex-col gap-3"
                aria-label="company ideas"
              >
                {brief.companies.map((company) => (
                  <SectorCompanyRow
                    key={`${company.name}:${company.ticker ?? "—"}`}
                    company={company}
                    runId={runId}
                  />
                ))}
              </ul>
            </BandBody>
          </Band>
        ) : null}

        {brief.watch_items.length > 0 ? (
          <Band>
            <BandHeader
              title="WATCH ITEMS"
              count={brief.watch_items.length}
            />
            <BandBody>
              <ul
                className="flex flex-col gap-3"
                data-testid="sector-watch-items"
              >
                {brief.watch_items.map((item) => (
                  <SectorWatchItemRow
                    key={item.name}
                    item={item}
                    runId={runId}
                  />
                ))}
              </ul>
            </BandBody>
          </Band>
        ) : null}

        {brief.cited_claims.length > 0 ? (
          <Band>
            <BandHeader
              title="CITED CLAIMS"
              count={brief.cited_claims.length}
            />
            <BandBody>
              <ul
                className="flex flex-col gap-3"
                data-testid="sector-cited-claims"
              >
                {brief.cited_claims.map((claim) => (
                  <SectorCitedClaimRow
                    key={`${claim.chunk_id}-${claim.exact_quote.slice(0, 32)}`}
                    claim={claim}
                    chunk={chunkById.get(claim.chunk_id) ?? null}
                  />
                ))}
              </ul>
            </BandBody>
          </Band>
        ) : null}
      </CardContent>
    </Card>
  );
}

interface BandProps {
  children: ReactNode;
}

function Band(props: BandProps): ReactElement {
  return (
    <section className="border-t border-line/60 first:border-t-0">
      {props.children}
    </section>
  );
}

interface BandHeaderProps {
  title: string;
  count?: number;
}

function BandHeader(props: BandHeaderProps): ReactElement {
  const { title, count } = props;
  return (
    <div className="flex items-baseline justify-between gap-3 px-6 pt-5 pb-3">
      <CapsLabel className="text-fg-muted">{title}</CapsLabel>
      {count !== undefined ? (
        <span className="font-mono tabular-nums text-xs text-fg-subtle">
          {count}
        </span>
      ) : null}
    </div>
  );
}

interface BandBodyProps {
  children: ReactNode;
  className?: string;
}

function BandBody(props: BandBodyProps): ReactElement {
  const { children, className } = props;
  return (
    <div className={`px-6 pb-6 ${className ?? ""}`.trim()}>{children}</div>
  );
}

interface SectorThemeRowProps {
  theme: Theme;
  runId?: string;
}

function SectorThemeRow(props: SectorThemeRowProps): ReactElement {
  const { theme, runId } = props;
  const { button, list } = useEvidenceDisclosure(
    theme.evidence_ids,
    "sector-theme",
    runId,
  );

  return (
    <li
      data-testid="sector-theme-row"
      className="rounded-md border border-line/40 bg-surface-2/30 px-4 py-3"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-fg text-sm truncate">{theme.name}</span>
          {button}
        </div>
        <span className="font-mono tabular-nums text-fg-muted text-sm shrink-0">
          {theme.confidence.toFixed(2)}
        </span>
      </div>
      {list}
    </li>
  );
}

interface SectorWatchItemRowProps {
  item: WatchItem;
  runId?: string;
}

function SectorWatchItemRow(props: SectorWatchItemRowProps): ReactElement {
  const { item, runId } = props;
  const { hasEvidence, button, list } = useEvidenceDisclosure(
    item.evidence_ids,
    "sector-watch-item",
    runId,
  );

  return (
    <li
      data-testid="sector-watch-item-row"
      className="rounded-md border border-line/40 bg-surface-2/30 px-4 py-4"
    >
      <p className="text-fg text-sm font-medium">{item.name}</p>
      <p className="mt-2 text-sm text-fg-muted leading-relaxed">
        {item.reason}
      </p>
      {hasEvidence ? (
        <div className="mt-3">
          {button}
          {list}
        </div>
      ) : null}
    </li>
  );
}

interface SectorCompanyRowProps {
  company: SectorCompanyIdea;
  runId?: string;
}

function SectorCompanyRow(props: SectorCompanyRowProps): ReactElement {
  const { company, runId } = props;
  const { button, list } = useEvidenceDisclosure(
    company.evidence_ids,
    "sector-company",
    runId,
  );

  const companyName =
    runId !== undefined &&
    company.company_entity_id !== null &&
    company.company_entity_id !== undefined ? (
      <Link
        href={
          `/research/runs/${runId}/companies/${company.company_entity_id}` as Route
        }
        className="text-fg hover:text-accent-text hover:underline transition-colors duration-150"
        data-testid="sector-company-link"
      >
        {company.name}
      </Link>
    ) : (
      <span className="text-fg">{company.name}</span>
    );

  return (
    <li
      data-testid="sector-company-row"
      className="rounded-md border border-line/40 bg-surface-2/30 px-4 py-3 font-mono text-xs"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          {companyName}
          {button}
        </div>
        <span className="text-fg-subtle shrink-0">{company.ticker ?? "—"}</span>
      </div>
      {list}
    </li>
  );
}

interface SectorCitedClaimRowProps {
  claim: CitedClaim;
  chunk: ChunkLookup | null;
}

function SectorCitedClaimRow(props: SectorCitedClaimRowProps): ReactElement {
  const { claim, chunk } = props;
  const [isOpen, setIsOpen] = useState<boolean>(false);

  const handleToggle = (): void => {
    setIsOpen((previous) => !previous);
  };

  const chunkPreview =
    chunk !== null && chunk.text.length > CHUNK_PREVIEW_LENGTH
      ? `${chunk.text.slice(0, CHUNK_PREVIEW_LENGTH)}…`
      : (chunk?.text ?? "");

  return (
    <li
      className="rounded-md border border-line bg-surface-2/40 px-4 py-3"
      data-testid="sector-cited-claim-row"
    >
      <button
        type="button"
        onClick={handleToggle}
        aria-expanded={isOpen}
        className="flex w-full items-start justify-between gap-3 text-left transition-colors duration-150 hover:text-accent-text"
      >
        <span className="text-sm text-fg leading-relaxed">
          {claim.claim_text}
        </span>
        <span className="shrink-0 text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
          {claim.source}
        </span>
      </button>
      {isOpen ? (
        <div className="mt-4 flex flex-col gap-3">
          <p className="rounded-md bg-canvas border border-line p-3 text-sm text-fg italic leading-relaxed">
            &ldquo;{claim.exact_quote}&rdquo;
          </p>
          {chunk !== null ? (
            <p className="text-xs text-fg-muted leading-relaxed">
              <span className="font-mono uppercase tracking-[0.14em] text-fg-subtle">
                Chunk:
              </span>{" "}
              {chunkPreview}
            </p>
          ) : null}
          <p className="text-xs text-fg-muted leading-relaxed font-mono">
            <span className="uppercase tracking-[0.14em] text-fg-subtle">
              Evidence:
            </span>{" "}
            <Link
              href={`/research/evidence/${claim.chunk_id}` as Route}
              className="text-accent-text hover:underline"
              data-testid="sector-cited-claim-chunk-link"
            >
              {claim.chunk_id}
            </Link>
          </p>
        </div>
      ) : null}
    </li>
  );
}
