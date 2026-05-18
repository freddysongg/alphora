"use client";

import { useState, useTransition } from "react";
import type { ReactElement } from "react";
import { toast } from "sonner";

import { HoldButton } from "@/components/ui";
import { cancelResearchRun } from "./actions";

export interface CancelRunButtonProps {
  runId: string;
  onOptimisticCancel: () => void;
  onCancelRollback: () => void;
}

export function CancelRunButton(props: CancelRunButtonProps): ReactElement {
  const { runId, onOptimisticCancel, onCancelRollback } = props;
  const [isPending, startTransition] = useTransition();
  const [hasCancelled, setHasCancelled] = useState(false);

  const handleHoldComplete = (): void => {
    if (isPending || hasCancelled) {
      return;
    }
    setHasCancelled(true);
    onOptimisticCancel();
    startTransition(async () => {
      const result = await cancelResearchRun(runId);
      if (!result.ok) {
        setHasCancelled(false);
        onCancelRollback();
        toast.error(`Cancel failed: ${result.error}`);
      }
    });
  };

  return (
    <HoldButton
      label="cancel run"
      onComplete={handleHoldComplete}
      disabled={hasCancelled || isPending}
    />
  );
}
