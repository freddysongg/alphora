"use client";

import { useState } from "react";
import type { ReactElement } from "react";
import type { Route } from "next";
import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle, CapsLabel } from "@/components/ui";
import { useEvidenceDisclosure } from "@/components/research/evidence-disclosure";
import type { components } from "@/lib/api";

type SectorBriefPublic = components["schemas"]["SectorBriefPublic"];
type CitedClaim = components["schemas"]["CitedClaim"];
type SectorCompanyIdea = components["schemas"]["SectorCompanyIdea"];
type Theme = components["schemas"]["Theme"];
type WatchItem = components["schemas"]["WatchItem"];

const DIRECTION_TONE: Record<string, string> = {
  overweight: "text-success",
  underweight: "text-danger",
  neutral: "text-fg-subtle",
};

export interface SectorBriefCardProps {
  sectorBrief: SectorBriefPublic;
}

export function SectorBriefCard(props: SectorBriefCardProps): ReactElement {
  const { sectorBrief } = props;
  const { brief, judge } = sectorBrief;
  const directionTone = DIRECTION_TONE[brief.direction] ?? "text-fg";
  const convictionPct = Math.round(
    Math.max(0, Math.min(1, brief.confidence)) * 100,
  );

  return (
    <Card data-testid="sector-brief-card">
      <CardHeader>
        <CardTitle>{brief.sector_name}</CardTitle>
        <CapsLabel className={directionTone}>{brief.direction}</CapsLabel>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-2">
          <CapsLabel className="text-fg-subtle">CONVICTION</CapsLabel>
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
          <span className="font-mono text-xs text-fg tabular-nums">
            {convictionPct}%
          </span>
        </div>
        <div className="flex items-center gap-2">
          <CapsLabel className="text-fg-subtle">JUDGE</CapsLabel>
          <span className="font-mono text-xs text-fg">{judge.status}</span>
        </div>
        {brief.themes.length > 0 ? (
          <div className="space-y-2" data-testid="sector-themes">
            <CapsLabel className="text-fg-subtle">THEMES</CapsLabel>
            <ul className="flex flex-col gap-2">
              {brief.themes.map((theme) => (
                <SectorThemeRow key={theme.name} theme={theme} />
              ))}
            </ul>
          </div>
        ) : null}
        {brief.companies.length > 0 ? (
          <ul className="flex flex-col gap-2" aria-label="company ideas">
            {brief.companies.map((company) => (
              <SectorCompanyRow
                key={`${company.name}:${company.ticker ?? "—"}`}
                company={company}
              />
            ))}
          </ul>
        ) : null}
        {brief.watch_items.length > 0 ? (
          <div className="space-y-2" data-testid="sector-watch-items">
            <CapsLabel className="text-fg-subtle">WATCH ITEMS</CapsLabel>
            <ul className="flex flex-col gap-2">
              {brief.watch_items.map((item) => (
                <SectorWatchItemRow key={item.name} item={item} />
              ))}
            </ul>
          </div>
        ) : null}
        {brief.cited_claims.length > 0 ? (
          <div className="space-y-2" data-testid="sector-cited-claims">
            <CapsLabel className="text-fg-subtle">CITED CLAIMS</CapsLabel>
            <ul className="flex flex-col gap-2">
              {brief.cited_claims.map((claim) => (
                <SectorCitedClaimRow
                  key={`${claim.chunk_id}-${claim.exact_quote.slice(0, 32)}`}
                  claim={claim}
                />
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

interface SectorThemeRowProps {
  theme: Theme;
}

function SectorThemeRow(props: SectorThemeRowProps): ReactElement {
  const { theme } = props;
  const { button, list } = useEvidenceDisclosure(
    theme.evidence_ids,
    "sector-theme",
  );

  return (
    <li
      data-testid="sector-theme-row"
      className="border-b border-line/60 pb-2 last:border-0 last:pb-0"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="text-fg text-sm">{theme.name}</span>
          {button}
        </div>
        <span className="font-mono tabular-nums text-fg-muted text-sm">
          {theme.confidence.toFixed(2)}
        </span>
      </div>
      {list}
    </li>
  );
}

interface SectorWatchItemRowProps {
  item: WatchItem;
}

function SectorWatchItemRow(props: SectorWatchItemRowProps): ReactElement {
  const { item } = props;
  const { hasEvidence, button, list } = useEvidenceDisclosure(
    item.evidence_ids,
    "sector-watch-item",
  );

  return (
    <li
      data-testid="sector-watch-item-row"
      className="border-b border-line/60 pb-2 last:border-0 last:pb-0"
    >
      <p className="text-fg text-sm font-medium">{item.name}</p>
      <p className="mt-1 text-sm text-fg-muted leading-relaxed">{item.reason}</p>
      {hasEvidence ? (
        <div className="mt-2">
          {button}
          {list}
        </div>
      ) : null}
    </li>
  );
}

interface SectorCompanyRowProps {
  company: SectorCompanyIdea;
}

function SectorCompanyRow(props: SectorCompanyRowProps): ReactElement {
  const { company } = props;
  const { button, list } = useEvidenceDisclosure(
    company.evidence_ids,
    "sector-company",
  );

  return (
    <li
      data-testid="sector-company-row"
      className="font-mono text-xs border-b border-line/60 pb-2 last:border-0 last:pb-0"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="text-fg">{company.name}</span>
          {button}
        </div>
        <span className="text-fg-subtle">{company.ticker ?? "—"}</span>
      </div>
      {list}
    </li>
  );
}

interface SectorCitedClaimRowProps {
  claim: CitedClaim;
}

function SectorCitedClaimRow(props: SectorCitedClaimRowProps): ReactElement {
  const { claim } = props;
  const [isOpen, setIsOpen] = useState<boolean>(false);

  const handleToggle = (): void => {
    setIsOpen((previous) => !previous);
  };

  return (
    <li
      className="rounded-md border border-line bg-surface-2/40 p-3"
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
        <div className="mt-3 flex flex-col gap-2">
          <p className="rounded-md bg-canvas border border-line p-3 text-sm text-fg italic leading-relaxed">
            &ldquo;{claim.exact_quote}&rdquo;
          </p>
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
