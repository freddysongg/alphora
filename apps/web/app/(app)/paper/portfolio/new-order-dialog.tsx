"use client";

import { useActionState, useCallback, useId, useState } from "react";
import type { ReactElement } from "react";
import { useFormStatus } from "react-dom";
import { Plus } from "@phosphor-icons/react/dist/ssr";
import { toast } from "sonner";

import {
  Button,
  CapsLabel,
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui";
import type { components } from "@/lib/api";
import { initialSubmitOrderState, submitPaperOrder } from "./actions";
import type { SubmitOrderActionState } from "./actions";

type OrderSide = components["schemas"]["OrderSideEnum"];
type OrderType = components["schemas"]["OrderTypeEnum"];

const labelClasses =
  "text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted";

interface SideOption {
  value: OrderSide;
  label: string;
  isDisabled: boolean;
}

interface TypeOption {
  value: OrderType;
  label: string;
}

const sideOptions: readonly SideOption[] = [
  { value: "buy", label: "Buy", isDisabled: false },
  { value: "sell", label: "Sell (long-only)", isDisabled: true },
];

const typeOptions: readonly TypeOption[] = [
  { value: "market", label: "Market" },
];

export interface NewOrderDialogProps {
  portfolioId: string | null;
}

interface SubmitButtonProps {
  isDisabled: boolean;
}

function SubmitButton(props: SubmitButtonProps): ReactElement {
  const { isDisabled } = props;
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant="primary" disabled={isDisabled || pending}>
      {pending ? "Submitting…" : "Submit"}
    </Button>
  );
}

export function NewOrderDialog(props: NewOrderDialogProps): ReactElement {
  const { portfolioId } = props;
  const [isOpen, setIsOpen] = useState(false);
  const [side, setSide] = useState<OrderSide>("buy");
  const [orderType, setOrderType] = useState<OrderType>("market");
  const tickerId = useId();
  const quantityId = useId();
  const tickerErrorId = useId();
  const quantityErrorId = useId();
  const sideErrorId = useId();
  const orderTypeErrorId = useId();

  const handleSubmit = useCallback(
    async (
      previousState: SubmitOrderActionState,
      formData: FormData,
    ): Promise<SubmitOrderActionState> => {
      const next = await submitPaperOrder(previousState, formData);
      if (next.status === "ok") {
        toast.success("Order submitted.");
        setIsOpen(false);
      } else if (next.status === "error" && next.message !== null) {
        toast.error(next.message);
      }
      return next;
    },
    [],
  );

  const [state, formAction] = useActionState(
    handleSubmit,
    initialSubmitOrderState,
  );

  const isPortfolioMissing = portfolioId === null;

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button variant="primary" disabled={isPortfolioMissing}>
          <Plus size={14} weight="regular" />
          New Order
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New paper order</DialogTitle>
        </DialogHeader>
        <form action={formAction} className="flex flex-col gap-4">
          <input
            type="hidden"
            name="portfolio_id"
            value={portfolioId ?? ""}
          />
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
            <CapsLabel>SIDE</CapsLabel>
            <Select
              name="side"
              value={side}
              onValueChange={(next) => setSide(next as OrderSide)}
            >
              <SelectTrigger
                aria-invalid={state.fields.side !== undefined}
                aria-describedby={
                  state.fields.side !== undefined ? sideErrorId : undefined
                }
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {sideOptions.map((option) => (
                  <SelectItem
                    key={option.value}
                    value={option.value}
                    disabled={option.isDisabled}
                  >
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {state.fields.side !== undefined ? (
              <p id={sideErrorId} className="text-xs text-danger">
                {state.fields.side.join(" ")}
              </p>
            ) : null}
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor={quantityId} className={labelClasses}>
              Quantity
            </label>
            <Input
              id={quantityId}
              name="quantity"
              type="number"
              placeholder="0"
              min={1}
              step={1}
              required
              aria-invalid={state.fields.quantity !== undefined}
              aria-describedby={
                state.fields.quantity !== undefined
                  ? quantityErrorId
                  : undefined
              }
            />
            {state.fields.quantity !== undefined ? (
              <p id={quantityErrorId} className="text-xs text-danger">
                {state.fields.quantity.join(" ")}
              </p>
            ) : null}
          </div>
          <div className="flex flex-col gap-2">
            <CapsLabel>ORDER TYPE</CapsLabel>
            <Select
              name="order_type"
              value={orderType}
              onValueChange={(next) => setOrderType(next as OrderType)}
            >
              <SelectTrigger
                aria-invalid={state.fields.order_type !== undefined}
                aria-describedby={
                  state.fields.order_type !== undefined
                    ? orderTypeErrorId
                    : undefined
                }
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {typeOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {state.fields.order_type !== undefined ? (
              <p id={orderTypeErrorId} className="text-xs text-danger">
                {state.fields.order_type.join(" ")}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="ghost">
                Cancel
              </Button>
            </DialogClose>
            <SubmitButton isDisabled={isPortfolioMissing} />
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
