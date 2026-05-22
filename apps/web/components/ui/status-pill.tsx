import type { ReactElement } from "react";
import { cn } from "@/lib/cn";

export type StatusPillStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "paused";

export interface StatusPillProps {
  status: StatusPillStatus;
  label?: string;
  className?: string;
}

interface StatusStyle {
  textClass: string;
  bgClass: string;
  dotClass: string;
  dotShadow: string;
  defaultLabel: string;
  isPulsing: boolean;
}

const styles: Record<StatusPillStatus, StatusStyle> = {
  pending: {
    textClass: "text-[var(--color-status-pending)]",
    bgClass: "bg-[rgba(185,140,255,0.12)]",
    dotClass: "bg-[var(--color-status-pending)]",
    dotShadow: "0 0 6px rgba(185,140,255,0.6)",
    defaultLabel: "Pending",
    isPulsing: false,
  },
  running: {
    textClass: "text-[var(--color-status-running)]",
    bgClass: "bg-[rgba(185,140,255,0.12)]",
    dotClass: "bg-[var(--color-status-running)]",
    dotShadow: "0 0 6px rgba(185,140,255,0.6)",
    defaultLabel: "Running",
    isPulsing: true,
  },
  succeeded: {
    textClass: "text-[var(--color-status-success)]",
    bgClass: "bg-[rgba(94,212,138,0.12)]",
    dotClass: "bg-[var(--color-status-success)]",
    dotShadow: "0 0 6px rgba(94,212,138,0.6)",
    defaultLabel: "Succeeded",
    isPulsing: false,
  },
  failed: {
    textClass: "text-[var(--color-status-failed)]",
    bgClass: "bg-[rgba(255,107,122,0.12)]",
    dotClass: "bg-[var(--color-status-failed)]",
    dotShadow: "0 0 6px rgba(255,107,122,0.6)",
    defaultLabel: "Failed",
    isPulsing: false,
  },
  cancelled: {
    textClass: "text-[var(--color-status-cancelled)]",
    bgClass: "bg-[rgba(128,122,150,0.14)]",
    dotClass: "bg-[var(--color-status-cancelled)]",
    dotShadow: "0 0 4px rgba(128,122,150,0.5)",
    defaultLabel: "Cancelled",
    isPulsing: false,
  },
  paused: {
    textClass: "text-[var(--color-status-paused)]",
    bgClass: "bg-[rgba(232,121,249,0.12)]",
    dotClass: "bg-[var(--color-status-paused)]",
    dotShadow: "0 0 6px rgba(232,121,249,0.6)",
    defaultLabel: "Paused",
    isPulsing: false,
  },
};

export function StatusPill(props: StatusPillProps): ReactElement {
  const { status, label, className } = props;
  const style = styles[status];
  const resolvedLabel = label ?? style.defaultLabel;
  return (
    <span
      aria-label={resolvedLabel}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-[3px] text-[11px] font-semibold leading-none",
        style.textClass,
        style.bgClass,
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "inline-block h-1.5 w-1.5 rounded-full",
          style.dotClass,
          style.isPulsing && "pulse-dot",
        )}
        style={{ boxShadow: style.dotShadow }}
      />
      <span>{resolvedLabel}</span>
    </span>
  );
}
