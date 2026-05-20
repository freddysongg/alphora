"use client";

import { useMemo, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import type { Route } from "next";
import Link from "next/link";

import {
  CapsLabel,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui";
import { SectorBriefCard } from "@/components/research/sector-brief-card";
import { useEvidenceDisclosure } from "@/components/research/evidence-disclosure";
import type { components } from "@/lib/api";
import { cn } from "@/lib/cn";

type MacroBriefPublic = components["schemas"]["MacroBriefPublic"];
type ChunkLookup = components["schemas"]["ChunkLookup"];
type CitedClaim = components["schemas"]["CitedClaim"];
type SectorCall = components["schemas"]["SectorCall"];
type Theme = components["schemas"]["Theme"];
type WatchItem = components["schemas"]["WatchItem"];
type ProposedHypothesis = components["schemas"]["ProposedHypothesis"];
type VerifierStatus = components["schemas"]["VerifierStatus"];
type JudgeStatus = components["schemas"]["JudgeStatus"];

const verifierStatusToClass: Record<VerifierStatus, string> = {
  verified: "bg-accent-deep/30 border border-accent-press text-accent-text",
  quote_unverified: "bg-warn/15 border border-warn/40 text-warn",
};

const verifierStatusToLabel: Record<VerifierStatus, string> = {
  verified: "VERIFIED",
  quote_unverified: "QUOTE UNVERIFIED",
};

const judgeStatusToClass: Record<JudgeStatus, string> = {
  passed: "bg-success/15 border border-success/40 text-success",
  flagged: "bg-warn/15 border border-warn/40 text-warn",
  not_run: "bg-surface-2 border border-line text-fg-subtle",
};

const judgeStatusToLabel: Record<JudgeStatus, string> = {
  passed: "JUDGE PASSED",
  flagged: "JUDGE FLAGGED",
  not_run: "JUDGE NOT RUN",
};

const CHUNK_PREVIEW_LENGTH = 200;

export interface MacroBriefDetailProps {
  data: MacroBriefPublic;
}

export function MacroBriefDetail(props: MacroBriefDetailProps): ReactElement {
  const { data } = props;
  const { brief, chunks, judge, sector_briefs: sectorBriefs } = data;

  const chunkById = useMemo(() => {
    const map = new Map<string, ChunkLookup>();
    for (const chunk of chunks) {
      map.set(chunk.chunk_id, chunk);
    }
    return map;
  }, [chunks]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-center justify-between gap-2">
        <CapsLabel as="h2">MACRO BRIEF</CapsLabel>
        <div className="flex items-center gap-2">
          <VerifierBadge
            status={brief.verifier_status}
            regenerationCount={brief.regeneration_count}
          />
          <JudgeBadge status={judge.status} />
        </div>
      </header>

      <Section title="THEMES">
        {brief.themes.length === 0 ? (
          <Empty />
        ) : (
          <ul className="flex flex-col gap-2">
            {brief.themes.map((theme) => (
              <ThemeRow key={theme.name} theme={theme} />
            ))}
          </ul>
        )}
      </Section>

      <Section title="SECTOR CALLS">
        {brief.sector_calls.length === 0 ? (
          <Empty />
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-line">
                <th
                  scope="col"
                  className="py-2 px-3 text-left text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted"
                >
                  Sector
                </th>
                <th
                  scope="col"
                  className="py-2 px-3 text-left text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted"
                >
                  Direction
                </th>
                <th
                  scope="col"
                  className="py-2 px-3 text-right text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted"
                >
                  Conviction
                </th>
                <th
                  scope="col"
                  className="py-2 px-3 text-right text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted"
                >
                  Evidence
                </th>
              </tr>
            </thead>
            <tbody>
              {brief.sector_calls.map((call) => (
                <SectorCallRow key={call.sector_entity_id} call={call} />
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title="WATCH ITEMS">
        {brief.watch_items.length === 0 ? (
          <Empty />
        ) : (
          <ul className="flex flex-col gap-2">
            {brief.watch_items.map((item) => (
              <WatchItemRow key={item.name} item={item} />
            ))}
          </ul>
        )}
      </Section>

      <Section title="CITED CLAIMS">
        {brief.cited_claims.length === 0 ? (
          <Empty />
        ) : (
          <ul className="flex flex-col gap-3">
            {brief.cited_claims.map((claim) => (
              <CitedClaimRow
                key={`${claim.chunk_id}-${claim.exact_quote.slice(0, 32)}`}
                claim={claim}
                chunk={chunkById.get(claim.chunk_id) ?? null}
              />
            ))}
          </ul>
        )}
      </Section>

      <Section title="PROPOSED HYPOTHESES">
        {brief.proposed_hypotheses.length === 0 ? (
          <Empty />
        ) : (
          <ul className="flex flex-col gap-2">
            {brief.proposed_hypotheses.map((hypothesis, index) => (
              <HypothesisRow
                key={`${hypothesis.claim_text}-${index}`}
                hypothesis={hypothesis}
              />
            ))}
          </ul>
        )}
      </Section>

      <Section title="SECTOR BRIEFS">
        {sectorBriefs.length === 0 ? (
          <Empty />
        ) : (
          <div className="flex flex-col gap-3">
            {sectorBriefs.map((sectorBrief) => (
              <SectorBriefCard
                key={sectorBrief.brief.sector_entity_id}
                sectorBrief={sectorBrief}
              />
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}

interface JudgeBadgeProps {
  status: JudgeStatus;
}

function JudgeBadge(props: JudgeBadgeProps): ReactElement {
  const { status } = props;
  return (
    <span
      data-testid="judge-badge"
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-[11px] tracking-[0.14em] font-medium uppercase font-mono",
        judgeStatusToClass[status],
      )}
    >
      {judgeStatusToLabel[status]}
    </span>
  );
}

interface VerifierBadgeProps {
  status: VerifierStatus;
  regenerationCount: number;
}

function VerifierBadge(props: VerifierBadgeProps): ReactElement {
  const { status, regenerationCount } = props;
  const suffix = regenerationCount > 0 ? ` (REGEN ${regenerationCount})` : "";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-[11px] tracking-[0.14em] font-medium uppercase font-mono",
        verifierStatusToClass[status],
      )}
    >
      {verifierStatusToLabel[status]}
      {suffix}
    </span>
  );
}

interface SectionProps {
  title: string;
  children: ReactNode;
}

function Section(props: SectionProps): ReactElement {
  const { title, children } = props;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function Empty(): ReactElement {
  return <p className="text-sm text-fg-subtle">No data.</p>;
}

interface ThemeRowProps {
  theme: Theme;
}

function ThemeRow(props: ThemeRowProps): ReactElement {
  const { theme } = props;
  const { button, list } = useEvidenceDisclosure(
    theme.evidence_ids,
    "macro-theme",
  );

  return (
    <li
      data-testid="macro-theme-row"
      className="border-b border-line/60 pb-2 last:border-0 last:pb-0"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="text-fg">{theme.name}</span>
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

interface WatchItemRowProps {
  item: WatchItem;
}

function WatchItemRow(props: WatchItemRowProps): ReactElement {
  const { item } = props;
  const { hasEvidence, button, list } = useEvidenceDisclosure(
    item.evidence_ids,
    "macro-watch-item",
  );

  return (
    <li
      data-testid="macro-watch-item-row"
      className="border-b border-line/60 pb-2 last:border-0 last:pb-0"
    >
      <p className="text-fg font-medium">{item.name}</p>
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

interface HypothesisRowProps {
  hypothesis: ProposedHypothesis;
}

function HypothesisRow(props: HypothesisRowProps): ReactElement {
  const { hypothesis } = props;
  const { hasEvidence, button, list } = useEvidenceDisclosure(
    hypothesis.evidence_ids,
    "macro-hypothesis",
  );

  return (
    <li
      data-testid="macro-hypothesis-row"
      className="text-sm text-fg leading-relaxed border-b border-line/60 pb-2 last:border-0 last:pb-0"
    >
      <p>{hypothesis.claim_text}</p>
      {hasEvidence ? (
        <div className="mt-2">
          {button}
          {list}
        </div>
      ) : null}
    </li>
  );
}

interface SectorCallRowProps {
  call: SectorCall;
}

function SectorCallRow(props: SectorCallRowProps): ReactElement {
  const { call } = props;
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const evidenceCount = call.evidence_ids.length;
  const hasEvidence = evidenceCount > 0;

  const handleToggle = (): void => {
    setIsOpen((previous) => !previous);
  };

  return (
    <tr
      data-testid="macro-sector-call-row"
      className="border-b border-line/60 align-top"
    >
      <td className="px-3 py-2 text-fg">{call.sector_name}</td>
      <td className="px-3 py-2 text-fg-muted uppercase tracking-[0.08em] text-[12px]">
        {call.direction}
      </td>
      <td className="px-3 py-2 text-right font-mono tabular-nums text-fg">
        {call.conviction.toFixed(2)}
      </td>
      <td className="px-3 py-2 text-right font-mono tabular-nums text-fg-muted">
        {hasEvidence ? (
          <>
            <button
              type="button"
              onClick={handleToggle}
              aria-expanded={isOpen}
              className="font-mono tabular-nums text-fg-muted hover:text-accent-text transition-colors duration-150"
            >
              {evidenceCount}
            </button>
            {isOpen ? (
              <ul className="mt-2 flex flex-col gap-1 text-right text-xs">
                {call.evidence_ids.map((evidenceId) => (
                  <li key={evidenceId} className="font-mono">
                    <Link
                      href={`/research/evidence/by-evidence/${evidenceId}` as Route}
                      className="text-accent-text hover:underline"
                      data-testid="macro-sector-call-evidence-link"
                    >
                      {evidenceId}
                    </Link>
                  </li>
                ))}
              </ul>
            ) : null}
          </>
        ) : (
          evidenceCount
        )}
      </td>
    </tr>
  );
}

interface CitedClaimRowProps {
  claim: CitedClaim;
  chunk: ChunkLookup | null;
}

function CitedClaimRow(props: CitedClaimRowProps): ReactElement {
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
      className="rounded-md border border-line bg-surface-2/40 p-3"
      data-testid="macro-cited-claim-row"
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
              data-testid="macro-cited-claim-chunk-link"
            >
              {claim.chunk_id}
            </Link>
          </p>
        </div>
      ) : null}
    </li>
  );
}
