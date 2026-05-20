"use client";

import { useState } from "react";
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

type CompanyThesisPublic = components["schemas"]["CompanyThesisPublic"];
type CompanyCatalyst = components["schemas"]["CompanyCatalyst"];
type CompanyRisk = components["schemas"]["CompanyRisk"];
type CitedClaim = components["schemas"]["CitedClaim"];
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

const directionToTone: Record<SectorCallDirection, string> = {
  overweight: "text-success",
  underweight: "text-danger",
  neutral: "text-fg-subtle",
};

export interface CompanyThesisDetailProps {
  data: CompanyThesisPublic;
}

export function CompanyThesisDetail(
  props: CompanyThesisDetailProps,
): ReactElement {
  const { data } = props;
  const { thesis, judge } = data;
  const convictionPct = Math.round(
    Math.max(0, Math.min(1, thesis.conviction)) * 100,
  );

  return (
    <div className="flex flex-col gap-6" data-testid="company-thesis-detail">
      <header className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <CapsLabel as="h2">COMPANY THESIS</CapsLabel>
          <div className="flex items-center gap-2">
            <VerifierBadge
              status={thesis.verifier_status}
              regenerationCount={thesis.regeneration_count}
            />
            <JudgeBadge status={judge.status} />
          </div>
        </div>
        <div className="flex flex-wrap items-baseline gap-3">
          <span className="text-xl text-fg font-medium">
            {thesis.company_name}
          </span>
          <span className="font-mono text-sm text-fg-muted">
            {thesis.ticker ?? "—"}
          </span>
          <span className="text-sm text-fg-subtle">{thesis.sector_name}</span>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <CapsLabel className={directionToTone[thesis.direction]}>
            {thesis.direction}
          </CapsLabel>
          <CapsLabel className="text-fg-subtle">CONVICTION</CapsLabel>
          <div
            role="progressbar"
            aria-label="conviction"
            aria-valuenow={convictionPct}
            aria-valuemin={0}
            aria-valuemax={100}
            className="h-1 w-40 bg-surface-2 rounded-full overflow-hidden"
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
      </header>

      <Section title="BULL CASE">
        <p className="text-sm text-fg leading-relaxed">{thesis.bull_case}</p>
      </Section>

      <Section title="BEAR CASE">
        <p className="text-sm text-fg leading-relaxed">{thesis.bear_case}</p>
      </Section>

      <Section title="CATALYSTS">
        {thesis.catalysts.length === 0 ? (
          <Empty />
        ) : (
          <ul className="flex flex-col gap-2">
            {thesis.catalysts.map((catalyst, index) => (
              <CatalystRow
                key={`${catalyst.name}-${index}`}
                catalyst={catalyst}
              />
            ))}
          </ul>
        )}
      </Section>

      <Section title="RISKS">
        {thesis.risks.length === 0 ? (
          <Empty />
        ) : (
          <ul className="flex flex-col gap-2">
            {thesis.risks.map((risk, index) => (
              <RiskRow key={`${risk.name}-${index}`} risk={risk} />
            ))}
          </ul>
        )}
      </Section>

      <Section title="CITED CLAIMS">
        {thesis.cited_claims.length === 0 ? (
          <Empty />
        ) : (
          <ul className="flex flex-col gap-3">
            {thesis.cited_claims.map((claim) => (
              <CitedClaimRow
                key={`${claim.chunk_id}-${claim.exact_quote.slice(0, 32)}`}
                claim={claim}
              />
            ))}
          </ul>
        )}
      </Section>

      <Section title="EVIDENCE">
        <ThesisEvidenceRow evidenceIds={thesis.evidence_ids} />
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

interface CatalystRowProps {
  catalyst: CompanyCatalyst;
}

function CatalystRow(props: CatalystRowProps): ReactElement {
  const { catalyst } = props;
  const { hasEvidence, button, list } = useEvidenceDisclosure(
    catalyst.evidence_ids,
    "company-catalyst",
  );

  return (
    <li
      data-testid="company-catalyst-row"
      className="border-b border-line/60 pb-2 last:border-0 last:pb-0"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-fg font-medium">{catalyst.name}</span>
          {catalyst.expected_timing !== null ? (
            <span className="text-xs text-fg-muted">
              {catalyst.expected_timing}
            </span>
          ) : null}
        </div>
        {hasEvidence ? <div>{button}</div> : null}
      </div>
      {list}
    </li>
  );
}

interface RiskRowProps {
  risk: CompanyRisk;
}

function RiskRow(props: RiskRowProps): ReactElement {
  const { risk } = props;
  const { hasEvidence, button, list } = useEvidenceDisclosure(
    risk.evidence_ids,
    "company-risk",
  );

  return (
    <li
      data-testid="company-risk-row"
      className="border-b border-line/60 pb-2 last:border-0 last:pb-0"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="text-fg font-medium">{risk.name}</span>
          {hasEvidence ? button : null}
        </div>
        <span className="font-mono tabular-nums text-fg-muted text-sm">
          {risk.severity.toFixed(2)}
        </span>
      </div>
      {list}
    </li>
  );
}

interface ThesisEvidenceRowProps {
  evidenceIds: readonly string[];
}

function ThesisEvidenceRow(props: ThesisEvidenceRowProps): ReactElement {
  const { evidenceIds } = props;
  const { hasEvidence, button, list } = useEvidenceDisclosure(
    evidenceIds,
    "company-thesis",
  );

  return (
    <div data-testid="company-thesis-evidence-row">
      {hasEvidence ? (
        <>
          {button}
          {list}
        </>
      ) : (
        <Empty />
      )}
    </div>
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
      data-testid="company-cited-claim-row"
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
              data-testid="company-cited-claim-chunk-link"
            >
              {claim.chunk_id}
            </Link>
          </p>
        </div>
      ) : null}
    </li>
  );
}
