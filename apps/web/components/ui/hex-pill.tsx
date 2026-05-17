import type { HTMLAttributes, ReactElement } from "react";
import { cn } from "@/lib/cn";

export interface HexPillProps extends HTMLAttributes<HTMLSpanElement> {
  value: string;
}

const baseClasses =
  "inline-flex items-center bg-surface border border-line rounded-md px-1.5 py-0.5 font-mono text-xs text-fg-muted";

export function HexPill(props: HexPillProps): ReactElement {
  const { value, className, ...rest } = props;
  return (
    <span className={cn(baseClasses, className)} {...rest}>
      {value}
    </span>
  );
}
