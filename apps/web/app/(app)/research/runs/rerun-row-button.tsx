"use client";

import { useTransition } from "react";
import type { ReactElement } from "react";
import { toast } from "sonner";
import { ArrowsClockwise } from "@phosphor-icons/react/dist/ssr";

import { Button } from "@/components/ui";
import { rerunResearchRun } from "./[id]/actions";

export interface RerunRowButtonProps {
  runId: string;
  ticker: string;
}

export function RerunRowButton(props: RerunRowButtonProps): ReactElement {
  const { runId, ticker } = props;
  const [isPending, startTransition] = useTransition();

  const handleClick = (): void => {
    if (isPending) {
      return;
    }
    startTransition(async () => {
      const result = await rerunResearchRun(runId);
      if (!result.ok) {
        toast.error(`Re-run failed: ${result.error}`);
      }
    });
  };

  return (
    <Button
      size="sm"
      variant="ghost"
      aria-label={`Re-run ${ticker}`}
      onClick={handleClick}
      disabled={isPending}
    >
      <ArrowsClockwise size={12} weight="regular" />
    </Button>
  );
}
