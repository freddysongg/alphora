"use client";

import { useTransition } from "react";
import type { ReactElement } from "react";
import { toast } from "sonner";

import { HoldButton } from "@/components/ui";
import { rerunResearchRun } from "./actions";

export interface RerunButtonProps {
  runId: string;
}

export function RerunButton(props: RerunButtonProps): ReactElement {
  const { runId } = props;
  const [isPending, startTransition] = useTransition();

  const handleHoldComplete = (): void => {
    if (isPending) {
      return;
    }
    startTransition(async () => {
      const result = await rerunResearchRun(runId);
      if (!result.ok) {
        toast.error(`Run again failed: ${result.error}`);
      }
    });
  };

  return (
    <HoldButton
      label="run again"
      onComplete={handleHoldComplete}
      disabled={isPending}
    />
  );
}
