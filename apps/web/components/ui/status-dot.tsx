import type { ReactElement } from "react";
import { cn } from "@/lib/cn";
import { chartAlphas } from "@/lib/tokens";

export type StatusKind = "live" | "pending" | "succeeded" | "failed" | "stale";

export interface StatusDotProps {
  status: StatusKind;
  label?: string;
  className?: string;
}

interface StatusStyle {
  dotClass: string;
  labelClass: string;
  defaultLabel: string;
  haloShadow?: string;
}

const styles: Record<StatusKind, StatusStyle> = {
  live: {
    dotClass: "bg-accent",
    labelClass: "text-fg",
    defaultLabel: "Live",
    haloShadow: `0 0 0 4px ${chartAlphas.liveHalo}`,
  },
  pending: {
    dotClass: "border border-fg-muted bg-transparent",
    labelClass: "text-fg-muted",
    defaultLabel: "Pending",
  },
  succeeded: {
    dotClass: "bg-accent",
    labelClass: "text-fg",
    defaultLabel: "Succeeded",
  },
  failed: {
    dotClass: "bg-danger",
    labelClass: "text-fg",
    defaultLabel: "Failed",
  },
  stale: {
    dotClass: "bg-warn",
    labelClass: "text-warn",
    defaultLabel: "Stale",
  },
};

export function StatusDot(props: StatusDotProps): ReactElement {
  const { status, label, className } = props;
  const style = styles[status];
  const resolvedLabel = label ?? style.defaultLabel;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 text-xs font-medium",
        style.labelClass,
        className,
      )}
      aria-label={resolvedLabel}
    >
      <span
        aria-hidden="true"
        className={cn("inline-block h-1.5 w-1.5 rounded-full", style.dotClass)}
        style={style.haloShadow ? { boxShadow: style.haloShadow } : undefined}
      />
      <span>{resolvedLabel}</span>
    </span>
  );
}
