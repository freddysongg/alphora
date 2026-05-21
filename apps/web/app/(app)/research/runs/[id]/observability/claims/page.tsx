import type { Metadata } from "next";
import type { ReactElement } from "react";
import type { Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "@phosphor-icons/react/dist/ssr";

import { Button, HexPill } from "@/components/ui";
import type { InlineClaim } from "@/components/research/inline-claim-review";
import type { components } from "@/lib/api";
import { InlineClaimReviewSection } from "../inline-claim-review-section";
import { defaultWeekStart, loadMacroBrief, loadRunDetail } from "../loaders";

export const metadata: Metadata = {
  title: "Claim Review · Alphora",
};

export const dynamic = "force-dynamic";

type MacroBriefPublic = components["schemas"]["MacroBriefPublic"];
type CitedClaim = components["schemas"]["CitedClaim"];

interface PageProps {
  params: Promise<{ id: string }>;
}

const INLINE_CLAIM_LIMIT = 20;

function projectClaims(
  macroBrief: MacroBriefPublic | null,
): readonly InlineClaim[] {
  if (macroBrief === null) {
    return [];
  }
  const seenChunkIds = new Set<string>();
  const projected: InlineClaim[] = [];
  const claims: readonly CitedClaim[] = macroBrief.brief.cited_claims;
  for (const claim of claims) {
    if (seenChunkIds.has(claim.chunk_id)) {
      continue;
    }
    seenChunkIds.add(claim.chunk_id);
    projected.push({
      chunkId: claim.chunk_id,
      quote: claim.exact_quote,
      briefKind: "macro",
      briefId: null,
      source: claim.source,
    });
    if (projected.length >= INLINE_CLAIM_LIMIT) {
      break;
    }
  }
  return projected;
}

export default async function ClaimsObservabilityPage(
  props: PageProps,
): Promise<ReactElement> {
  const { id } = await props.params;
  const detail = await loadRunDetail(id);
  if (detail === null) {
    notFound();
  }
  const isFunnel = detail.strategy === "funnel_research";
  const macroBrief = isFunnel ? await loadMacroBrief(id) : null;
  const claims = projectClaims(macroBrief);
  const observabilityHref = `/research/runs/${id}/observability` as Route;
  return (
    <div className="max-w-[1100px] mx-auto">
      <header className="sticky top-0 z-10 bg-canvas border-b border-line">
        <div className="flex items-center gap-4 px-6 py-4">
          <Button
            asChild
            size="sm"
            variant="ghost"
            aria-label="Back to observability"
          >
            <Link href={observabilityHref}>
              <ArrowLeft size={12} weight="regular" />
            </Link>
          </Button>
          <span className="text-2xl font-mono tabular-nums text-fg">
            CLAIM REVIEW
          </span>
          <HexPill value={detail.id} />
        </div>
      </header>

      <div className="px-6 pt-6 pb-12">
        {claims.length === 0 ? (
          <p className="text-sm text-fg-muted">
            No cited claims to review for this run.
          </p>
        ) : (
          <InlineClaimReviewSection
            runId={detail.id}
            defaultWeekStart={defaultWeekStart()}
            claims={claims}
          />
        )}
      </div>
    </div>
  );
}
