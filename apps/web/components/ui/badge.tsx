import type { HTMLAttributes, ReactElement } from "react";
import { cn } from "@/lib/cn";

export type BadgeVariant = "buy" | "hold" | "sell" | "none";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant: BadgeVariant;
}

const variantClasses: Record<BadgeVariant, string> = {
  buy: "bg-accent-deep text-canvas",
  hold: "bg-surface border border-line text-fg-muted",
  sell: "bg-danger/20 text-danger",
  none: "border border-dashed border-line text-fg-subtle",
};

const variantLabels: Record<BadgeVariant, string> = {
  buy: "BUY",
  hold: "HOLD",
  sell: "SELL",
  none: "—",
};

const baseClasses =
  "inline-flex items-center text-[11px] tracking-[0.14em] font-medium uppercase px-2 py-0.5 rounded-md font-mono";

export function Badge(props: BadgeProps): ReactElement {
  const { variant, className, children, ...rest } = props;
  return (
    <span className={cn(baseClasses, variantClasses[variant], className)} {...rest}>
      {children ?? variantLabels[variant]}
    </span>
  );
}
