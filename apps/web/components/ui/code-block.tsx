"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import { Check, Copy } from "@phosphor-icons/react/dist/ssr";
import { cn } from "@/lib/cn";

export interface CodeBlockProps {
  children: string;
  lang?: string;
  className?: string;
  hasCopy?: boolean;
}

const COMMENT_PATTERN = /^(\s*)(#|\/\/).*$/;
const COPY_RESET_MS = 1200;

function renderHighlightedLine(line: string, index: number): ReactElement {
  const isComment = COMMENT_PATTERN.test(line);
  return (
    <span
      key={`${index}-${line.length}`}
      className={cn("block", isComment ? "text-fg-subtle" : "text-fg")}
    >
      {line.length === 0 ? " " : line}
    </span>
  );
}

export function CodeBlock(props: CodeBlockProps): ReactElement {
  const { children, lang, className, hasCopy = true } = props;
  const [isCopied, setIsCopied] = useState(false);
  const resetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (resetTimerRef.current !== null) {
        clearTimeout(resetTimerRef.current);
      }
    };
  }, []);

  const handleCopy = useCallback(async (): Promise<void> => {
    if (typeof navigator === "undefined" || !navigator.clipboard) {
      return;
    }
    await navigator.clipboard.writeText(children);
    setIsCopied(true);
    if (resetTimerRef.current !== null) {
      clearTimeout(resetTimerRef.current);
    }
    resetTimerRef.current = setTimeout(() => {
      setIsCopied(false);
    }, COPY_RESET_MS);
  }, [children]);

  const lines = children.split("\n");

  return (
    <div
      className={cn(
        "relative bg-canvas border border-line border-t-accent rounded-md overflow-hidden",
        className,
      )}
    >
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <div className="flex items-center gap-1.5" aria-hidden="true">
          <span className="h-2.5 w-2.5 rounded-full bg-line" />
          <span className="h-2.5 w-2.5 rounded-full bg-line" />
          <span className="h-2.5 w-2.5 rounded-full bg-line" />
        </div>
        {lang ? (
          <span className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-subtle">
            {lang}
          </span>
        ) : null}
        {hasCopy ? (
          <button
            type="button"
            onClick={handleCopy}
            aria-label={isCopied ? "Copied" : "Copy code"}
            className="inline-flex h-6 w-6 items-center justify-center rounded-md text-fg-muted hover:text-fg hover:bg-surface transition-colors duration-150 press-scale"
          >
            {isCopied ? (
              <Check size={12} weight="regular" />
            ) : (
              <Copy size={12} weight="regular" />
            )}
          </button>
        ) : null}
      </div>
      <pre className="overflow-x-auto p-4 font-mono text-[12px] leading-5">
        <code>{lines.map(renderHighlightedLine)}</code>
      </pre>
    </div>
  );
}
