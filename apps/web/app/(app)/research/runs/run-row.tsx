import type { ReactElement } from "react";
import Link from "next/link";
import type { Route } from "next";
import { Eye } from "@phosphor-icons/react/dist/ssr";
import {
  Badge,
  Button,
  HexPill,
  StatusDot,
} from "@/components/ui";
import type { BadgeVariant } from "@/components/ui";
import type { components } from "@/lib/api";
import { isTerminal, runStatusToStatusKind } from "@/lib/research/status-mapping";
import { RerunRowButton } from "./rerun-row-button";

type ResearchRunSummary = components["schemas"]["ResearchRunSummary"];
type FinalRating = NonNullable<ResearchRunSummary["final_rating"]>;
type ScopePayload = ResearchRunSummary["scope_payload"];

const ratingToBadge: Record<FinalRating, BadgeVariant> = {
  buy: "buy",
  hold: "hold",
  sell: "sell",
  none: "none",
};

const SCOPE_UNIVERSE_LABEL: Record<string, string> = {
  us_equities: "US EQUITIES",
};

function resolveBadgeVariant(
  rating: ResearchRunSummary["final_rating"],
): BadgeVariant {
  if (rating === null) {
    return "none";
  }
  return ratingToBadge[rating];
}

function resolveScopeLabel(scope: ScopePayload): string | null {
  if (scope === null || scope === undefined) {
    return null;
  }
  const kind = (scope as Record<string, unknown>)["kind"];
  const universe = (scope as Record<string, unknown>)["universe"];
  if (typeof kind !== "string" || typeof universe !== "string") {
    return null;
  }
  const universeLabel = SCOPE_UNIVERSE_LABEL[universe] ?? universe.toUpperCase();
  return `${kind.toUpperCase()} · ${universeLabel}`;
}

function resolveRunLabel(run: ResearchRunSummary): string {
  if (run.strategy === "funnel_research") {
    const scopeLabel = resolveScopeLabel(run.scope_payload);
    if (scopeLabel !== null) {
      return scopeLabel;
    }
  }
  return run.ticker ?? "—";
}

export interface RunRowProps {
  run: ResearchRunSummary;
}

export function RunRow(props: RunRowProps): ReactElement {
  const { run } = props;
  const href = `/research/runs/${run.id}` as Route;
  const runLabel = resolveRunLabel(run);
  const isFunnelRun = run.strategy === "funnel_research";
  return (
    <li className="group flex items-center gap-4 px-3 py-3 border-b border-line/60 hover:bg-surface-2 transition-colors duration-150">
      <Link
        href={href}
        className="flex flex-1 items-center gap-4 min-w-0"
        aria-label={`Open run ${run.id} for ${runLabel}`}
      >
        <span
          className={
            isFunnelRun
              ? "font-mono text-xs text-fg w-48 shrink-0 tracking-wider"
              : "font-mono text-base text-fg w-20 shrink-0"
          }
        >
          {runLabel}
        </span>
        <HexPill value={run.id} />
        <StatusDot status={runStatusToStatusKind(run.status)} />
        <div className="flex-1" />
        <Badge variant={resolveBadgeVariant(run.final_rating)} />
      </Link>
      <div className="flex items-center gap-1 shrink-0">
        {isTerminal(run.status) && run.ticker !== null ? (
          <RerunRowButton runId={run.id} ticker={run.ticker} />
        ) : null}
        <Button asChild size="sm" variant="ghost" aria-label={`View ${runLabel}`}>
          <Link href={href}>
            <Eye size={12} weight="regular" />
          </Link>
        </Button>
      </div>
    </li>
  );
}
