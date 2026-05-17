"use client";

import type { ReactElement } from "react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";

export interface ActivityStripProps {
  buckets: number[];
  className?: string;
  height?: number;
  startTimestampIso?: string;
  bucketDurationMs?: number;
}

const HOUR_MS = 60 * 60 * 1000;
const MIN_BAR_RATIO = 0.06;

function formatBucketLabel(
  startIso: string | undefined,
  durationMs: number,
  index: number,
): string {
  if (!startIso) {
    return `Bucket ${index}`;
  }
  const start = new Date(startIso);
  if (Number.isNaN(start.getTime())) {
    return `Bucket ${index}`;
  }
  const stamp = new Date(start.getTime() + durationMs * index);
  return stamp.toISOString().replace("T", " ").replace(/\.\d+Z$/, "Z");
}

export function ActivityStrip(props: ActivityStripProps): ReactElement {
  const {
    buckets,
    className,
    height = 32,
    startTimestampIso,
    bucketDurationMs = HOUR_MS,
  } = props;
  const maxValue = buckets.reduce((acc, bucket) => Math.max(acc, bucket), 0);

  return (
    <TooltipProvider delayDuration={300}>
      <div
        className={cn("inline-flex items-end gap-[2px]", className)}
        style={{ height }}
        role="img"
        aria-label="Activity over time"
      >
        {buckets.map((count, index) => {
          const ratio = maxValue === 0 ? 0 : count / maxValue;
          const visualRatio = count === 0 ? 0 : Math.max(ratio, MIN_BAR_RATIO);
          const bucketLabel = formatBucketLabel(
            startTimestampIso,
            bucketDurationMs,
            index,
          );
          return (
            <Tooltip key={`bucket-${index}`}>
              <TooltipTrigger asChild>
                <span
                  className="block w-[3px] rounded-[1px] bg-accent"
                  style={{
                    height: `${visualRatio * 100}%`,
                    opacity: count === 0 ? 0.25 : 1,
                  }}
                />
              </TooltipTrigger>
              <TooltipContent>
                <span className="font-mono">
                  {bucketLabel} · {count}
                </span>
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </TooltipProvider>
  );
}
