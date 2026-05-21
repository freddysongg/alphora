"use client";

import { useCallback, useState } from "react";
import type { ReactElement } from "react";
import { useRouter } from "next/navigation";

import {
  InlineClaimReview,
  type InlineClaim,
} from "@/components/research/inline-claim-review";
import { Input } from "@/components/ui";

export interface InlineClaimReviewSectionProps {
  runId: string;
  defaultWeekStart: string;
  claims: readonly InlineClaim[];
}

export function InlineClaimReviewSection(
  props: InlineClaimReviewSectionProps,
): ReactElement {
  const { runId, defaultWeekStart, claims } = props;
  const router = useRouter();
  const [reviewer, setReviewer] = useState<string>("");

  const handleSubmitted = useCallback((): void => {
    router.refresh();
  }, [router]);

  return (
    <div className="flex flex-col gap-3">
      <label className="flex items-center gap-3 text-sm text-fg-muted">
        <span className="text-[11px] tracking-[0.14em] font-medium uppercase">
          REVIEWER
        </span>
        <Input
          type="text"
          value={reviewer}
          onChange={(event) => setReviewer(event.target.value)}
          placeholder="your name"
          className="max-w-xs"
        />
      </label>
      <InlineClaimReview
        runId={runId}
        defaultWeekStart={defaultWeekStart}
        reviewer={reviewer}
        claims={claims}
        onSubmitted={handleSubmitted}
      />
    </div>
  );
}
