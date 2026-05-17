"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import { ArrowDown, Check } from "@phosphor-icons/react/dist/ssr";
import { cn } from "@/lib/cn";

export type LogLevel = "info" | "warn" | "err";

export interface LogLine {
  id?: string;
  ts: string;
  level: LogLevel;
  message: string;
}

export interface LogViewerProps {
  lines: LogLine[];
  onLoadMore?: () => void;
  className?: string;
  initialFollow?: boolean;
}

const levelClasses: Record<LogLevel, string> = {
  info: "text-accent-soft",
  warn: "text-warn",
  err: "text-danger",
};

const levelLabels: Record<LogLevel, string> = {
  info: "INFO",
  warn: "WARN",
  err: "ERR ",
};

const SCROLL_NEAR_BOTTOM_PX = 24;

export function LogViewer(props: LogViewerProps): ReactElement {
  const { lines, onLoadMore, className, initialFollow = true } = props;
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [isFollowing, setIsFollowing] = useState(initialFollow);
  const [unseenCount, setUnseenCount] = useState(0);
  const lastSeenCountRef = useRef(lines.length);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) {
      return;
    }
    if (isFollowing) {
      node.scrollTop = node.scrollHeight;
      lastSeenCountRef.current = lines.length;
      setUnseenCount(0);
      return;
    }
    const added = lines.length - lastSeenCountRef.current;
    if (added > 0) {
      setUnseenCount((prev) => prev + added);
      lastSeenCountRef.current = lines.length;
    }
  }, [lines, isFollowing]);

  const handleScroll = useCallback((): void => {
    const node = scrollRef.current;
    if (!node) {
      return;
    }
    const distanceFromBottom =
      node.scrollHeight - node.scrollTop - node.clientHeight;
    const isNearBottom = distanceFromBottom <= SCROLL_NEAR_BOTTOM_PX;
    setIsFollowing(isNearBottom);
    if (isNearBottom) {
      setUnseenCount(0);
      lastSeenCountRef.current = lines.length;
    }
  }, [lines.length]);

  const jumpToBottom = useCallback((): void => {
    const node = scrollRef.current;
    if (!node) {
      return;
    }
    node.scrollTop = node.scrollHeight;
    setIsFollowing(true);
    setUnseenCount(0);
    lastSeenCountRef.current = lines.length;
  }, [lines.length]);

  return (
    <div
      className={cn(
        "relative bg-canvas border border-line rounded-md overflow-hidden",
        className,
      )}
    >
      <div className="absolute right-2 top-2 z-10 flex items-center gap-2">
        <button
          type="button"
          onClick={() => setIsFollowing((prev) => !prev)}
          aria-pressed={isFollowing}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md border border-line bg-surface px-2 py-1 text-[11px] tracking-[0.14em] font-medium uppercase transition-colors duration-150 press-scale",
            isFollowing
              ? "text-accent-text border-line-strong"
              : "text-fg-muted hover:text-fg",
          )}
        >
          {isFollowing ? <Check size={10} weight="regular" /> : null}
          Follow
        </button>
        {onLoadMore ? (
          <button
            type="button"
            onClick={onLoadMore}
            className="rounded-md border border-line bg-surface px-2 py-1 text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted hover:text-fg transition-colors duration-150 press-scale"
          >
            Load more
          </button>
        ) : null}
      </div>
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="max-h-[420px] overflow-y-auto p-3 font-mono text-[12px] leading-5"
      >
        {lines.map((line, index) => (
          <div
            key={line.id ?? `${line.ts}-${index}`}
            className="grid grid-cols-[100px_44px_1fr] gap-2"
          >
            <span className="text-fg-subtle tabular-nums">{line.ts}</span>
            <span
              className={cn(
                "text-[11px] tracking-[0.14em] font-medium uppercase",
                levelClasses[line.level],
              )}
            >
              {levelLabels[line.level]}
            </span>
            <span className="text-fg whitespace-pre-wrap break-all">
              {line.message}
            </span>
          </div>
        ))}
      </div>
      {!isFollowing && unseenCount > 0 ? (
        <button
          type="button"
          onClick={jumpToBottom}
          className="absolute bottom-3 right-3 inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-surface-2 px-2 py-1 text-xs text-fg shadow-[var(--shadow-popover)] hover:bg-surface transition-colors duration-150 press-scale"
        >
          <span className="font-mono tabular-nums">{unseenCount}</span>
          <span>new lines</span>
          <ArrowDown size={12} weight="regular" />
        </button>
      ) : null}
    </div>
  );
}
