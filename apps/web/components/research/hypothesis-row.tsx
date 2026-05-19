"use client";

import { useTransition } from "react";
import type { ReactElement } from "react";
import Link from "next/link";
import type { Route } from "next";
import { toast } from "sonner";

import { Button, CapsLabel, HexPill } from "@/components/ui";
import type { components } from "@/lib/api";
import { activateHypothesis } from "@/app/(app)/research/hypotheses/actions";

type HypothesisPublic = components["schemas"]["HypothesisPublic"];

export interface HypothesisRowProps {
  hypothesis: HypothesisPublic;
}

export function HypothesisRow(props: HypothesisRowProps): ReactElement {
  const { hypothesis } = props;
  const [isPending, startTransition] = useTransition();

  const isProposed = hypothesis.state === "proposed";
  const sourceRunHref =
    hypothesis.source_run_id !== null
      ? (`/research/runs/${hypothesis.source_run_id}` as Route)
      : null;

  const handleActivate = (): void => {
    if (isPending) {
      return;
    }
    startTransition(async () => {
      const result = await activateHypothesis(hypothesis.id);
      if (!result.ok) {
        toast.error(`Activate failed: ${result.error}`);
        return;
      }
      toast.success("Hypothesis activated.");
    });
  };

  return (
    <li className="flex items-center gap-4 px-3 py-3 border-b border-line/60 hover:bg-surface-2 transition-colors duration-150">
      <CapsLabel
        className={
          isProposed
            ? "text-fg-subtle w-24 shrink-0"
            : "text-accent w-24 shrink-0"
        }
      >
        {hypothesis.state}
      </CapsLabel>
      <p className="flex-1 min-w-0 text-sm text-fg truncate">
        {hypothesis.claim_text}
      </p>
      <HexPill value={hypothesis.id} />
      <span className="font-mono text-xs text-fg-subtle w-16 text-right tabular-nums">
        {hypothesis.scope_theme_ids.length} themes
      </span>
      <div className="flex items-center gap-1 shrink-0">
        {sourceRunHref !== null ? (
          <Button asChild size="sm" variant="ghost" aria-label="Open source run">
            <Link href={sourceRunHref}>Run</Link>
          </Button>
        ) : null}
        {isProposed ? (
          <Button
            size="sm"
            variant="default"
            onClick={handleActivate}
            disabled={isPending}
            aria-label={`Activate hypothesis ${hypothesis.id}`}
          >
            Activate
          </Button>
        ) : null}
      </div>
    </li>
  );
}
