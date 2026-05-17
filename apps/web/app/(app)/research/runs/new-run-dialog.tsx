"use client";

import { useActionState, useEffect, useId, useState } from "react";
import type { ReactElement } from "react";
import { useFormStatus } from "react-dom";
import { Plus } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import {
  Button,
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Input,
} from "@/components/ui";
import { createResearchRun, initialNewRunState } from "./actions";

const labelClasses =
  "text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted";

function todayIsoDate(): string {
  const now = new Date();
  const year = now.getUTCFullYear().toString().padStart(4, "0");
  const month = (now.getUTCMonth() + 1).toString().padStart(2, "0");
  const day = now.getUTCDate().toString().padStart(2, "0");
  return `${year}-${month}-${day}`;
}

interface SubmitButtonProps {
  isDisabled: boolean;
}

function SubmitButton(props: SubmitButtonProps): ReactElement {
  const { isDisabled } = props;
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant="primary" disabled={isDisabled || pending}>
      {pending ? "Enqueuing…" : "Enqueue run"}
    </Button>
  );
}

export function NewRunDialog(): ReactElement {
  const [isOpen, setIsOpen] = useState(false);
  const [state, formAction] = useActionState(
    createResearchRun,
    initialNewRunState,
  );
  const tickerId = useId();
  const tradeDateId = useId();
  const tickerErrorId = useId();
  const tradeDateErrorId = useId();
  const defaultTradeDate = todayIsoDate();

  useEffect(() => {
    if (state.status === "error" && state.message !== null) {
      toast.error(state.message);
    }
  }, [state]);

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
        <form action={formAction} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <label htmlFor={tickerId} className={labelClasses}>
              Ticker
            </label>
            <Input
              id={tickerId}
              name="ticker"
              placeholder="AAPL"
              autoComplete="off"
              spellCheck={false}
              required
              aria-invalid={state.fields.ticker !== undefined}
              aria-describedby={
                state.fields.ticker !== undefined ? tickerErrorId : undefined
              }
            />
            {state.fields.ticker !== undefined ? (
              <p id={tickerErrorId} className="text-xs text-danger">
                {state.fields.ticker.join(" ")}
              </p>
            ) : null}
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor={tradeDateId} className={labelClasses}>
              Trade date
            </label>
            <Input
              id={tradeDateId}
              name="trade_date"
              type="date"
              defaultValue={defaultTradeDate}
              required
              aria-invalid={state.fields.trade_date !== undefined}
              aria-describedby={
                state.fields.trade_date !== undefined
                  ? tradeDateErrorId
                  : undefined
              }
            />
            {state.fields.trade_date !== undefined ? (
              <p id={tradeDateErrorId} className="text-xs text-danger">
                {state.fields.trade_date.join(" ")}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="ghost">
                Cancel
              </Button>
            </DialogClose>
            <SubmitButton isDisabled={false} />
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
