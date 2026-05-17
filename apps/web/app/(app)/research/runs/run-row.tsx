import type { ReactElement } from "react";
import Link from "next/link";
import type { Route } from "next";
import { ArrowsClockwise, Eye } from "@phosphor-icons/react/dist/ssr";
import {
  Badge,
  Button,
  HexPill,
  StatusDot,
} from "@/components/ui";
import type { BadgeVariant } from "@/components/ui";
import type { components } from "@/lib/api";
import { runStatusToStatusKind } from "@/lib/research/status-mapping";

type ResearchRunSummary = components["schemas"]["ResearchRunSummary"];
type FinalRating = NonNullable<ResearchRunSummary["final_rating"]>;

const ratingToBadge: Record<FinalRating, BadgeVariant> = {
  buy: "buy",
  hold: "hold",
  sell: "sell",
  none: "none",
};

function resolveBadgeVariant(
  rating: ResearchRunSummary["final_rating"],
): BadgeVariant {
  if (rating === null) {
    return "none";
  }
  return ratingToBadge[rating];
}

export interface RunRowProps {
  run: ResearchRunSummary;
}

export function RunRow(props: RunRowProps): ReactElement {
  const { run } = props;
  const href = `/research/runs/${run.id}` as Route;
  return (
    <li className="group flex items-center gap-4 px-3 py-3 border-b border-line/60 hover:bg-surface-2 transition-colors duration-150">
      <Link
        href={href}
        className="flex flex-1 items-center gap-4 min-w-0"
        aria-label={`Open run ${run.id} for ${run.ticker}`}
      >
        <span className="font-mono text-base text-fg w-20 shrink-0">
          {run.ticker}
        </span>
        <HexPill value={run.id} />
        <StatusDot status={runStatusToStatusKind(run.status)} />
        <div className="flex-1" />
        <Badge variant={resolveBadgeVariant(run.final_rating)} />
      </Link>
      <div className="flex items-center gap-1 shrink-0">
        <Button
          size="sm"
          variant="ghost"
          aria-label={`Re-run ${run.ticker}`}
        >
          <ArrowsClockwise size={12} weight="regular" />
        </Button>
        <Button asChild size="sm" variant="ghost" aria-label={`View ${run.ticker}`}>
          <Link href={href}>
            <Eye size={12} weight="regular" />
          </Link>
        </Button>
      </div>
    </li>
  );
}
