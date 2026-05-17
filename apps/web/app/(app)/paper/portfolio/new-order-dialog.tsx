"use client";

import { useState } from "react";
import type { ReactElement } from "react";
import { Plus } from "@phosphor-icons/react/dist/ssr";
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
  HoldButton,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui";

type OrderSide = "buy" | "sell";
type OrderType = "market";

const labelClasses =
  "text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted";

const sideOptions: ReadonlyArray<{ value: OrderSide; label: string; disabled: boolean }> = [
  { value: "buy", label: "Buy", disabled: false },
  { value: "sell", label: "Sell (long-only)", disabled: true },
];

const typeOptions: ReadonlyArray<{ value: OrderType; label: string }> = [
  { value: "market", label: "Market" },
];

export function NewOrderDialog(): ReactElement {
  const [isOpen, setIsOpen] = useState(false);
  const [side, setSide] = useState<OrderSide>("buy");
  const [orderType, setOrderType] = useState<OrderType>("market");

  const handleComplete = (): void => {
    setIsOpen(false);
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button variant="primary">
          <Plus size={14} weight="regular" />
          New Order
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New paper order</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <label htmlFor="order-ticker" className={labelClasses}>
              Ticker
            </label>
            <Input
              id="order-ticker"
              placeholder="AAPL"
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <div className="flex flex-col gap-2">
            <CapsLabel>SIDE</CapsLabel>
            <Select value={side} onValueChange={(next) => setSide(next as OrderSide)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {sideOptions.map((option) => (
                  <SelectItem
                    key={option.value}
                    value={option.value}
                    disabled={option.disabled}
                  >
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor="order-qty" className={labelClasses}>
              Quantity
            </label>
            <Input
              id="order-qty"
              type="number"
              placeholder="0"
              min={0}
              step={1}
            />
          </div>
          <div className="flex flex-col gap-2">
            <CapsLabel>ORDER TYPE</CapsLabel>
            <Select
              value={orderType}
              onValueChange={(next) => setOrderType(next as OrderType)}
            >
              <SelectTrigger>
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
          </div>
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="ghost">Cancel</Button>
          </DialogClose>
          <HoldButton label="submit" onComplete={handleComplete} />
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
