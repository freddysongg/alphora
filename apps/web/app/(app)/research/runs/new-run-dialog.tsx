"use client";

import { useState } from "react";
import type { ReactElement } from "react";
import { Plus } from "@phosphor-icons/react/dist/ssr";
import {
  Button,
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  HoldButton,
  Input,
} from "@/components/ui";

const submitLabel = "Hold to run";
const labelClasses =
  "text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted";

export function NewRunDialog(): ReactElement {
  const [isOpen, setIsOpen] = useState(false);

  const handleComplete = (): void => {
    setIsOpen(false);
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button variant="primary">
          <Plus size={14} weight="regular" />
          New Run
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New research run</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <label htmlFor="new-run-ticker" className={labelClasses}>
            Ticker
          </label>
          <Input
            id="new-run-ticker"
            placeholder="AAPL"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="ghost">Cancel</Button>
          </DialogClose>
          <HoldButton label={submitLabel} onComplete={handleComplete} />
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
