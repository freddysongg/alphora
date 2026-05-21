"use client";

import { useEffect, useRef, useState } from "react";
import type {
  HTMLAttributes,
  KeyboardEvent,
  MouseEvent,
  ReactElement,
} from "react";

import { cn } from "@/lib/cn";

export interface HexPillProps
  extends Omit<HTMLAttributes<HTMLSpanElement>, "onClick"> {
  value: string;
  onClick?: (event: MouseEvent<HTMLSpanElement>) => void;
}

const baseClasses =
  "inline-flex items-center rounded-[5px] bg-[#1f1933] px-[7px] py-[2px] font-mono text-[11px] text-[#b3a8d8] transition-colors duration-150 hover:bg-[#2a2245] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent-text cursor-pointer";
const copiedClasses = "text-success";
const COPIED_FEEDBACK_MS = 1200;

function truncate(input: string): string {
  if (input.length <= 9) {
    return input;
  }
  const head = input.slice(0, 4);
  const tail = input.slice(-4);
  return `${head}…${tail}`;
}

async function copyToClipboard(text: string): Promise<boolean> {
  if (
    typeof navigator !== "undefined" &&
    navigator.clipboard !== undefined &&
    typeof navigator.clipboard.writeText === "function"
  ) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      return false;
    }
  }
  return false;
}

export function HexPill(props: HexPillProps): ReactElement {
  const { value, className, title, onClick, ...rest } = props;
  const [isCopied, setIsCopied] = useState<boolean>(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return (): void => {
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  const triggerCopy = (): void => {
    void copyToClipboard(value).then((ok) => {
      if (!ok) {
        return;
      }
      setIsCopied(true);
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current);
      }
      timeoutRef.current = setTimeout(() => {
        setIsCopied(false);
      }, COPIED_FEEDBACK_MS);
    });
  };

  const handleClick = (event: MouseEvent<HTMLSpanElement>): void => {
    event.preventDefault();
    event.stopPropagation();
    triggerCopy();
    if (onClick !== undefined) {
      onClick(event);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLSpanElement>): void => {
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    triggerCopy();
  };

  return (
    <span
      role="button"
      tabIndex={0}
      title={title ?? `${value} — click to copy`}
      aria-label={`copy ${value} to clipboard`}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={cn(baseClasses, isCopied ? copiedClasses : "", className)}
      data-copied={isCopied ? "true" : undefined}
      {...rest}
    >
      <span className="select-none">
        {isCopied ? "copied" : truncate(value)}
      </span>
    </span>
  );
}
