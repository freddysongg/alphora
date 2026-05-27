"use client";

import { useMemo, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import type { Route } from "next";
import Link from "next/link";

import { CapsLabel, Card } from "@/components/ui";
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
  runId?: string;
}

export function MacroBriefDetail(props: MacroBriefDetailProps): ReactElement {
  const { data, runId } = props;
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

      <Card className="p-0">
        <Band title="THEMES" count={brief.themes.length}>
          {brief.themes.length === 0 ? (
            <Empty />
          ) : (
            <ul className="flex flex-col">
              {brief.themes.map((theme) => (
                <ThemeRow key={theme.name} theme={theme} runId={runId} />
              ))}
            </ul>
          )}
        </Band>

        <Band title="SECTOR CALLS" count={brief.sector_calls.length}>
          {brief.sector_calls.length === 0 ? (
            <Empty />
          ) : (
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-line/60">
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
                  <SectorCallRow
                    key={call.sector_entity_id}
                    call={call}
                    runId={runId}
                  />
                ))}
              </tbody>
            </table>
          )}
        </Band>

        <Band title="WATCH ITEMS" count={brief.watch_items.length}>
          {brief.watch_items.length === 0 ? (
            <Empty />
          ) : (
            <ul className="flex flex-col">
              {brief.watch_items.map((item) => (
                <WatchItemRow key={item.name} item={item} runId={runId} />
              ))}
            </ul>
          )}
        </Band>

        <Band title="CITED CLAIMS" count={brief.cited_claims.length}>
          {brief.cited_claims.length === 0 ? (
            <Empty />
          ) : (
            <ul className="flex flex-col">
              {brief.cited_claims.map((claim) => (
                <CitedClaimRow
                  key={`${claim.chunk_id}-${claim.exact_quote.slice(0, 32)}`}
                  claim={claim}
                  chunk={chunkById.get(claim.chunk_id) ?? null}
                />
              ))}
            </ul>
          )}
        </Band>

        <Band
          title="PROPOSED HYPOTHESES"
          count={brief.proposed_hypotheses.length}
        >
          {brief.proposed_hypotheses.length === 0 ? (
            <Empty />
          ) : (
            <ul className="flex flex-col">
              {brief.proposed_hypotheses.map((hypothesis, index) => (
                <HypothesisRow
                  key={`${hypothesis.claim_text}-${index}`}
                  hypothesis={hypothesis}
                  runId={runId}
                />
              ))}
            </ul>
          )}
        </Band>
      </Card>

      {sectorBriefs.length > 0 ? (
        <section className="flex flex-col gap-4">
          <CapsLabel as="h3" className="px-1 text-fg-muted">
            SECTOR BRIEFS
          </CapsLabel>
          <div className="flex flex-col gap-4">
            {sectorBriefs.map((sectorBrief) => (
              <SectorBriefCard
                key={sectorBrief.brief.sector_entity_id}
                sectorBrief={sectorBrief}
                runId={runId}
              />
            ))}
          </div>
        </section>
      ) : null}
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

interface BandProps {
  title: string;
  count?: number;
  children: ReactNode;
}

function Band(props: BandProps): ReactElement {
  const { title, count, children } = props;
  return (
    <section className="border-t border-line/60 first:border-t-0">
      <div className="flex items-baseline justify-between gap-3 px-6 pt-5 pb-3">
        <CapsLabel className="text-fg-muted">{title}</CapsLabel>
        {count !== undefined ? (
          <span className="font-mono tabular-nums text-xs text-fg-subtle">
            {count}
          </span>
        ) : null}
      </div>
      <div className="px-6 pb-6">{children}</div>
    </section>
  );
}

function Empty(): ReactElement {
  return <p className="text-sm text-fg-subtle">No data.</p>;
}

interface ThemeRowProps {
  theme: Theme;
  runId?: string;
}

function ThemeRow(props: ThemeRowProps): ReactElement {
  const { theme, runId } = props;
  const { button, list } = useEvidenceDisclosure(
    theme.evidence_ids,
    "macro-theme",
    runId,
  );

  return (
    <li
      data-testid="macro-theme-row"
      className="border-t border-line/40 first:border-t-0 py-3"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4 min-w-0">
          <span className="text-fg">{theme.name}</span>
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

interface WatchItemRowProps {
  item: WatchItem;
  runId?: string;
}

function WatchItemRow(props: WatchItemRowProps): ReactElement {
  const { item, runId } = props;
  const { hasEvidence, button, list } = useEvidenceDisclosure(
    item.evidence_ids,
    "macro-watch-item",
    runId,
  );

  return (
    <li
      data-testid="macro-watch-item-row"
      className="border-t border-line/40 first:border-t-0 py-4"
    >
      <p className="text-fg font-medium">{item.name}</p>
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

interface HypothesisRowProps {
  hypothesis: ProposedHypothesis;
  runId?: string;
}

function HypothesisRow(props: HypothesisRowProps): ReactElement {
  const { hypothesis, runId } = props;
  const { hasEvidence, button, list } = useEvidenceDisclosure(
    hypothesis.evidence_ids,
    "macro-hypothesis",
    runId,
  );

  return (
    <li
      data-testid="macro-hypothesis-row"
      className="border-t border-line/40 first:border-t-0 py-4 text-sm text-fg leading-relaxed"
    >
      <p>{hypothesis.claim_text}</p>
      {hasEvidence ? (
        <div className="mt-3">
          {button}
          {list}
        </div>
      ) : null}
    </li>
  );
}

interface SectorCallRowProps {
  call: SectorCall;
  runId?: string;
}

function SectorCallRow(props: SectorCallRowProps): ReactElement {
  const { call, runId } = props;
  const { button, list } = useEvidenceDisclosure(
    call.evidence_ids,
    "macro-sector-call",
    runId,
    { variant: "count", align: "right" },
  );

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
        {button}
        {list}
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
      className="border-t border-line/40 first:border-t-0 py-3"
      data-testid="macro-cited-claim-row"
    >
      <button
        type="button"
        onClick={handleToggle}
        aria-expanded={isOpen}
        className="flex w-full items-start justify-between gap-3 text-left transition-colors duration-150 hover:text-highlight-text"
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
              className="text-highlight-text hover:underline"
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
