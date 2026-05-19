"use client";

import { useState, useTransition } from "react";
import type { ReactElement, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import {
  Button,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui";

import { createMacroBriefRun } from "./actions";

interface NewMacroBriefDialogProps {
  trigger: ReactNode;
}

function todayIsoDate(): string {
  const now = new Date();
  const year = now.getUTCFullYear().toString().padStart(4, "0");
  const month = (now.getUTCMonth() + 1).toString().padStart(2, "0");
  const day = now.getUTCDate().toString().padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function NewMacroBriefDialog(
  props: NewMacroBriefDialogProps,
): ReactElement {
  const { trigger } = props;
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const tradeDate = todayIsoDate();

  const handleConfirm = (): void => {
    if (isPending) {
      return;
    }
    startTransition(async () => {
      const result = await createMacroBriefRun({ tradeDate });
      if (!result.ok) {
        toast.error(`Failed to start macro brief: ${result.error}`);
        return;
      }
      setIsOpen(false);
      router.push(`/research/runs/${result.runId}`);
    });
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Run macro brief</DialogTitle>
          <DialogDescription>
            Runs the funnel_research Stage 1 synthesis for {tradeDate} over the
            US equities universe.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="ghost" disabled={isPending}>
              Cancel
            </Button>
          </DialogClose>
          <Button
            type="button"
            variant="primary"
            onClick={handleConfirm}
            disabled={isPending}
          >
            {isPending ? "Starting…" : "Start run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
