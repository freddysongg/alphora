"use client";

import { useState } from "react";
import type { ReactElement } from "react";
import type { Route } from "next";
import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle, CapsLabel } from "@/components/ui";
import type { components } from "@/lib/api";

type SectorBriefPublic = components["schemas"]["SectorBriefPublic"];
type CitedClaim = components["schemas"]["CitedClaim"];

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
        {brief.companies.length > 0 ? (
          <ul className="space-y-1" aria-label="company ideas">
            {brief.companies.map((company) => (
              <li
                key={`${company.name}:${company.ticker ?? "—"}`}
                className="flex items-center justify-between font-mono text-xs"
              >
                <span className="text-fg">{company.name}</span>
                <span className="text-fg-subtle">{company.ticker ?? "—"}</span>
              </li>
            ))}
          </ul>
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
