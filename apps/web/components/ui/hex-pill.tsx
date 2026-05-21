import type { HTMLAttributes, ReactElement } from "react";
import { cn } from "@/lib/cn";

export interface HexPillProps extends HTMLAttributes<HTMLSpanElement> {
  value: string;
}

const baseClasses =
  "inline-flex items-center bg-[#1f1933] rounded-[5px] px-[7px] py-[2px] font-mono text-[11px] text-[#b3a8d8] select-none";

function truncate(input: string): string {
  if (input.length <= 9) {
    return input;
  }
  const head = input.slice(0, 4);
  const tail = input.slice(-4);
  return `${head}…${tail}`;
}

export function HexPill(props: HexPillProps): ReactElement {
  const { value, className, title, ...rest } = props;
  return (
    <span
      title={title ?? value}
      className={cn(baseClasses, className)}
      {...rest}
    >
      {truncate(value)}
    </span>
  );
}
