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
import { useEvidenceDisclosure } from "@/components/research/evidence-disclosure";
import type { components } from "@/lib/api";
import { cn } from "@/lib/cn";

type PortfolioBriefPublic = components["schemas"]["PortfolioBriefPublic"];
type PortfolioSectorEntry = components["schemas"]["PortfolioSectorEntry"];
type PortfolioCompanyEntry = components["schemas"]["PortfolioCompanyEntry"];
type PortfolioCoverage = components["schemas"]["PortfolioCoverage"];
type PortfolioMacroSummary = components["schemas"]["PortfolioMacroSummary"];
type CitedClaim = components["schemas"]["CitedClaim"];
type Theme = components["schemas"]["Theme"];
type WatchItem = components["schemas"]["WatchItem"];
type VerifierStatus = components["schemas"]["VerifierStatus"];
type JudgeStatus = components["schemas"]["JudgeStatus"];
type SectorCallDirection = components["schemas"]["SectorCallDirection"];

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

const judgeStatusToShortLabel: Record<JudgeStatus, string> = {
  passed: "PASSED",
  flagged: "FLAGGED",
  not_run: "NOT RUN",
};

const directionToTone: Record<SectorCallDirection, string> = {
  overweight: "text-success",
  underweight: "text-danger",
  neutral: "text-fg-subtle",
};

export interface PortfolioBriefDetailProps {
  data: PortfolioBriefPublic;
}

export function PortfolioBriefDetail(
  props: PortfolioBriefDetailProps,
): ReactElement {
  const { data } = props;
  const { brief, judge } = data;

  return (
    <div className="flex flex-col gap-6" data-testid="portfolio-brief-detail">
      <header className="flex items-center justify-between gap-2">
        <CapsLabel as="h2">PORTFOLIO BRIEF</CapsLabel>
        <div className="flex items-center gap-2">
          <VerifierBadge
            status={brief.verifier_status}
            regenerationCount={brief.regeneration_count}
          />
          <JudgeBadge status={judge.status} />
        </div>
      </header>

      <Section title="COVERAGE">
        <CoverageGrid coverage={brief.coverage} />
      </Section>

      <Section title="MACRO SUMMARY">
        <MacroSummary macro={brief.macro} />
      </Section>

      <Section title="SECTORS">
        {brief.sectors.length === 0 ? (
          <Empty />
        ) : (
          <SectorTable entries={brief.sectors} />
        )}
      </Section>

      <Section title="COMPANIES">
        {brief.companies.length === 0 ? (
          <Empty />
        ) : (
          <CompanyTable entries={brief.companies} runId={brief.run_id} />
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
              />
            ))}
          </ul>
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

interface CoverageGridProps {
  coverage: PortfolioCoverage;
}

interface CoverageCell {
  label: string;
  value: number;
}

function CoverageGrid(props: CoverageGridProps): ReactElement {
  const { coverage } = props;
  const sectorCells: CoverageCell[] = [
    { label: "SELECTED", value: coverage.sectors_selected },
    { label: "VERIFIED", value: coverage.sectors_verified },
    { label: "JUDGE PASSED", value: coverage.sectors_judge_passed },
    { label: "JUDGE FLAGGED", value: coverage.sectors_judge_flagged },
  ];
  const companyCells: CoverageCell[] = [
    { label: "SELECTED", value: coverage.companies_selected },
    { label: "VERIFIED", value: coverage.companies_verified },
    { label: "JUDGE PASSED", value: coverage.companies_judge_passed },
    { label: "JUDGE FLAGGED", value: coverage.companies_judge_flagged },
  ];
  return (
    <div
      className="grid grid-cols-1 gap-6 md:grid-cols-2"
      data-testid="coverage-grid"
    >
      <CoverageBlock heading="SECTORS" cells={sectorCells} />
      <CoverageBlock heading="COMPANIES" cells={companyCells} />
    </div>
  );
}

interface CoverageBlockProps {
  heading: string;
  cells: readonly CoverageCell[];
}

function CoverageBlock(props: CoverageBlockProps): ReactElement {
  const { heading, cells } = props;
  return (
    <div>
      <CapsLabel className="text-fg-subtle">{heading}</CapsLabel>
      <dl className="mt-2 grid grid-cols-2 gap-3">
        {cells.map((cell) => (
          <div
            key={cell.label}
            className="rounded-md border border-line bg-surface-2/40 p-3"
          >
            <dt className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
              {cell.label}
            </dt>
            <dd className="mt-1 font-mono tabular-nums text-xl text-fg">
              {cell.value.toLocaleString()}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

interface MacroSummaryProps {
  macro: PortfolioMacroSummary;
}

function MacroSummary(props: MacroSummaryProps): ReactElement {
  const { macro } = props;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
          CONFIDENCE
        </span>
        <span className="font-mono tabular-nums text-fg">
          {macro.confidence.toFixed(2)}
        </span>
        <span className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
          MACRO JUDGE
        </span>
        <span
          data-testid="macro-judge-status"
          className={cn(
            "inline-flex items-center rounded-md px-2 py-0.5 text-[11px] tracking-[0.14em] font-medium uppercase font-mono",
            judgeStatusToClass[macro.judge_status],
          )}
        >
          {judgeStatusToShortLabel[macro.judge_status]}
        </span>
      </div>
      <ThemeList themes={macro.themes} />
      <WatchItemList items={macro.watch_items} />
    </div>
  );
}

interface ThemeListProps {
  themes: readonly Theme[];
}

function ThemeList(props: ThemeListProps): ReactElement {
  const { themes } = props;
  return (
    <div>
      <CapsLabel className="text-fg-subtle">THEMES</CapsLabel>
      {themes.length === 0 ? (
        <p className="mt-2 text-sm text-fg-subtle">No themes.</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-2">
          {themes.map((theme) => (
            <PortfolioMacroThemeRow key={theme.name} theme={theme} />
          ))}
        </ul>
      )}
    </div>
  );
}

interface WatchItemListProps {
  items: readonly WatchItem[];
}

function WatchItemList(props: WatchItemListProps): ReactElement {
  const { items } = props;
  return (
    <div>
      <CapsLabel className="text-fg-subtle">WATCH ITEMS</CapsLabel>
      {items.length === 0 ? (
        <p className="mt-2 text-sm text-fg-subtle">No watch items.</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-2">
          {items.map((item) => (
            <PortfolioMacroWatchItemRow key={item.name} item={item} />
          ))}
        </ul>
      )}
    </div>
  );
}

interface PortfolioMacroThemeRowProps {
  theme: Theme;
}

function PortfolioMacroThemeRow(
  props: PortfolioMacroThemeRowProps,
): ReactElement {
  const { theme } = props;
  const { button, list } = useEvidenceDisclosure(
    theme.evidence_ids,
    "portfolio-macro-theme",
  );

  return (
    <li
      data-testid="portfolio-macro-theme-row"
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

interface PortfolioMacroWatchItemRowProps {
  item: WatchItem;
}

function PortfolioMacroWatchItemRow(
  props: PortfolioMacroWatchItemRowProps,
): ReactElement {
  const { item } = props;
  const { hasEvidence, button, list } = useEvidenceDisclosure(
    item.evidence_ids,
    "portfolio-macro-watch-item",
  );

  return (
    <li
      data-testid="portfolio-macro-watch-item-row"
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

interface SectorTableProps {
  entries: readonly PortfolioSectorEntry[];
}

function SectorTable(props: SectorTableProps): ReactElement {
  const { entries } = props;
  const sorted = useMemo(
    () => [...entries].sort((a, b) => a.rank - b.rank),
    [entries],
  );
  return (
    <table
      className="w-full border-collapse text-sm"
      data-testid="sector-table"
    >
      <thead>
        <tr className="border-b border-line">
          <Th align="right">Rank</Th>
          <Th>Sector</Th>
          <Th>Direction</Th>
          <Th align="right">Conviction</Th>
          <Th>Verifier</Th>
          <Th>Judge</Th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((entry) => (
          <tr
            key={entry.sector_entity_id}
            className="h-10 border-b border-line/60"
          >
            <td className="px-3 text-right font-mono tabular-nums text-fg-muted">
              {entry.rank}
            </td>
            <td className="px-3 text-fg">{entry.sector_name}</td>
            <td
              className={cn(
                "px-3 uppercase tracking-[0.08em] text-[12px]",
                directionToTone[entry.direction],
              )}
            >
              {entry.direction}
            </td>
            <td className="px-3 text-right font-mono tabular-nums text-fg">
              {entry.conviction.toFixed(2)}
            </td>
            <td className="px-3 text-[11px] tracking-[0.14em] uppercase text-fg-muted font-mono">
              {verifierStatusToLabel[entry.verifier_status]}
            </td>
            <td className="px-3 text-[11px] tracking-[0.14em] uppercase font-mono">
              <span className={cn("inline-flex items-center", textForJudge(entry.judge_status))}>
                {judgeStatusToShortLabel[entry.judge_status]}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

interface CompanyTableProps {
  entries: readonly PortfolioCompanyEntry[];
  runId: string;
}

function CompanyTable(props: CompanyTableProps): ReactElement {
  const { entries, runId } = props;
  const sorted = useMemo(
    () => [...entries].sort((a, b) => a.rank - b.rank),
    [entries],
  );
  return (
    <table
      className="w-full border-collapse text-sm"
      data-testid="company-table"
    >
      <thead>
        <tr className="border-b border-line">
          <Th align="right">Rank</Th>
          <Th>Company</Th>
          <Th>Ticker</Th>
          <Th>Sector</Th>
          <Th>Direction</Th>
          <Th align="right">Conviction</Th>
          <Th>Verifier</Th>
          <Th>Judge</Th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((entry) => (
          <tr
            key={entry.company_entity_id}
            className="h-10 border-b border-line/60"
          >
            <td className="px-3 text-right font-mono tabular-nums text-fg-muted">
              {entry.rank}
            </td>
            <td className="px-3 text-fg">
              <Link
                href={
                  `/research/runs/${runId}/companies/${entry.company_entity_id}` as Route
                }
                className="text-fg hover:text-accent-text hover:underline transition-colors duration-150"
                data-testid="portfolio-company-link"
              >
                {entry.company_name}
              </Link>
            </td>
            <td className="px-3 font-mono text-fg-muted">
              {entry.ticker ?? "—"}
            </td>
            <td className="px-3 text-fg-muted">{entry.sector_name}</td>
            <td
              className={cn(
                "px-3 uppercase tracking-[0.08em] text-[12px]",
                directionToTone[entry.direction],
              )}
            >
              {entry.direction}
            </td>
            <td className="px-3 text-right font-mono tabular-nums text-fg">
              {entry.conviction.toFixed(2)}
            </td>
            <td className="px-3 text-[11px] tracking-[0.14em] uppercase text-fg-muted font-mono">
              {verifierStatusToLabel[entry.verifier_status]}
            </td>
            <td className="px-3 text-[11px] tracking-[0.14em] uppercase font-mono">
              <span className={cn("inline-flex items-center", textForJudge(entry.judge_status))}>
                {judgeStatusToShortLabel[entry.judge_status]}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function textForJudge(status: JudgeStatus): string {
  if (status === "passed") {
    return "text-success";
  }
  if (status === "flagged") {
    return "text-warn";
  }
  return "text-fg-subtle";
}

interface ThProps {
  children: ReactNode;
  align?: "left" | "right";
}

function Th(props: ThProps): ReactElement {
  const { children, align = "left" } = props;
  return (
    <th
      scope="col"
      className={cn(
        "py-2 px-3 text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      {children}
    </th>
  );
}

interface CitedClaimRowProps {
  claim: CitedClaim;
}

function CitedClaimRow(props: CitedClaimRowProps): ReactElement {
  const { claim } = props;
  const [isOpen, setIsOpen] = useState<boolean>(false);

  const handleToggle = (): void => {
    setIsOpen((previous) => !previous);
  };

  return (
    <li
      className="rounded-md border border-line bg-surface-2/40 p-3"
      data-testid="cited-claim-row"
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
              Chunk:
            </span>{" "}
            <Link
              href={`/research/evidence/${claim.chunk_id}` as Route}
              className="text-accent-text hover:underline"
              data-testid="cited-claim-chunk-link"
            >
              {claim.chunk_id}
            </Link>
          </p>
        </div>
      ) : null}
    </li>
  );
}
