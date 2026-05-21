"use client";

import type { ReactElement } from "react";
import Link from "next/link";
import type { Route } from "next";
import { ArrowRight } from "@phosphor-icons/react/dist/ssr";
import { Button, HexPill, StatusPill } from "@/components/ui";
import { cn } from "@/lib/cn";
import type { components } from "@/lib/api";
import { runStatusToStatusKind } from "@/lib/research/status-mapping";
import {
  FUNNEL_STAGES,
  FUNNEL_TOTAL_STAGES,
  getFunnelStageByIndex,
} from "@/lib/research/funnel-stages";
import { resolveScopeLabel } from "@/lib/research/scope";
import { useRunStageProgress } from "@/lib/research/use-run-stage-progress";

type ResearchRunSummary = components["schemas"]["ResearchRunSummary"];
type RunStatus = components["schemas"]["RunStatusEnum"];

type StageBarState = "done" | "active" | "pending" | "failed" | "dimmed";

const stageBarClasses: Record<StageBarState, string> = {
  done: "bg-[linear-gradient(90deg,#7a4dff,#9970ff)]",
  active: "bg-[#7a4dff] stage-pulse-glow",
  pending: "bg-[#1a1426]",
  failed: "bg-[#ff6b7a]",
  dimmed: "bg-[#1a1426] opacity-50",
};

function resolveRunLabel(run: ResearchRunSummary): string {
  if (run.strategy === "funnel_research") {
    return resolveScopeLabel(run.scope_payload) ?? "Funnel research";
  }
  return run.ticker ?? "—";
}

function deriveFunnelStageStates(
  status: RunStatus,
  liveStageIndex: number | null,
): StageBarState[] {
  if (status === "succeeded") {
    return Array.from({ length: FUNNEL_TOTAL_STAGES }, () => "done");
  }
  if (status === "queued") {
    return Array.from({ length: FUNNEL_TOTAL_STAGES }, () => "pending");
  }
  const stageIndex = liveStageIndex ?? (status === "running" ? 1 : null);
  if (status === "failed") {
    const failedAt = stageIndex ?? FUNNEL_TOTAL_STAGES;
    return Array.from({ length: FUNNEL_TOTAL_STAGES }, (_unused, idx) => {
      const oneBased = idx + 1;
      if (oneBased < failedAt) {
        return "done";
      }
      if (oneBased === failedAt) {
        return "failed";
      }
      return "dimmed";
    });
  }
  if (status === "cancelled") {
    const cancelledAt = stageIndex ?? FUNNEL_TOTAL_STAGES;
    return Array.from({ length: FUNNEL_TOTAL_STAGES }, (_unused, idx) => {
      const oneBased = idx + 1;
      if (oneBased < cancelledAt) {
        return "done";
      }
      return "dimmed";
    });
  }
  const activeAt = stageIndex ?? 1;
  return Array.from({ length: FUNNEL_TOTAL_STAGES }, (_unused, idx) => {
    const oneBased = idx + 1;
    if (oneBased < activeAt) {
      return "done";
    }
    if (oneBased === activeAt) {
      return "active";
    }
    return "pending";
  });
}

function formatRelativeTime(iso: string): string {
  const created = Date.parse(iso);
  if (Number.isNaN(created)) {
    return "—";
  }
  const elapsedMs = Date.now() - created;
  const minutes = Math.floor(elapsedMs / 60_000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function buildMetaLine(
  status: RunStatus,
  stageIndex: number | null,
  stageName: string | null,
  createdAt: string,
): string {
  const relative = formatRelativeTime(createdAt);
  if (status === "succeeded") {
    return `${FUNNEL_TOTAL_STAGES} / ${FUNNEL_TOTAL_STAGES} · ${relative}`;
  }
  if (status === "failed") {
    if (stageIndex !== null && stageName !== null) {
      return `Failed at ${stageIndex} / ${FUNNEL_TOTAL_STAGES} · ${stageName} · ${relative}`;
    }
    return `Failed · ${relative}`;
  }
  if (status === "cancelled") {
    if (stageIndex !== null) {
      return `Cancelled at ${stageIndex} / ${FUNNEL_TOTAL_STAGES} · ${relative}`;
    }
    return `Cancelled · ${relative}`;
  }
  if (status === "queued") {
    return `Queued · ${relative}`;
  }
  if (stageIndex !== null && stageName !== null) {
    return `Stage ${stageIndex} / ${FUNNEL_TOTAL_STAGES} · ${stageName}`;
  }
  return `Running · ${relative}`;
}

export interface RunRowProps {
  run: ResearchRunSummary;
}

export function RunRow(props: RunRowProps): ReactElement {
  const { run } = props;
  const href = `/research/runs/${run.id}` as Route;
  const runLabel = resolveRunLabel(run);
  const isFunnelRun = run.strategy === "funnel_research";
  const progress = useRunStageProgress(run.id, run.status);
  const currentStage =
    progress.stageIndex !== null
      ? getFunnelStageByIndex(progress.stageIndex)
      : null;

  return (
    <li>
      <Link
        href={href}
        aria-label={`Open run ${run.id} for ${runLabel}`}
        className="group block rounded-[10px] border border-[#2a2440] bg-[#14121f] px-4 py-3.5 transition-colors duration-150 hover:border-[#3a2a5a]"
      >
        <div className="flex items-center gap-3">
          <span className="text-[14px] font-semibold text-[#f0eafa] truncate">
            {runLabel}
          </span>
          <HexPill value={run.id} />
          <div className="flex-1" />
          <StatusPill status={runStatusToStatusKind(run.status)} />
          <Button
            asChild
            variant="ghost"
            shape="icon"
            size="sm"
            aria-label={`Open ${runLabel}`}
            className="group-hover:text-fg"
          >
            <span>
              <ArrowRight size={12} weight="regular" />
            </span>
          </Button>
        </div>
        {isFunnelRun ? (
          <FunnelStageRail
            status={run.status}
            liveStageIndex={progress.stageIndex}
            liveStageName={currentStage?.name ?? null}
          />
        ) : (
          <NonFunnelStageBar status={run.status} />
        )}
        <div className="mt-2.5 flex items-center justify-between font-mono text-[11px] text-[#807a96]">
          <span>
            {isFunnelRun
              ? buildMetaLine(
                  run.status,
                  progress.stageIndex,
                  currentStage?.name ?? null,
                  run.created_at,
                )
              : nonFunnelMetaLine(run.status, run.created_at)}
          </span>
        </div>
      </Link>
    </li>
  );
}

interface FunnelStageRailProps {
  status: RunStatus;
  liveStageIndex: number | null;
  liveStageName: string | null;
}

function FunnelStageRail(props: FunnelStageRailProps): ReactElement {
  const { status, liveStageIndex, liveStageName } = props;
  const states = deriveFunnelStageStates(status, liveStageIndex);
  return (
    <div className="mt-3">
      <div className="flex items-center gap-1">
        {states.map((state, idx) => (
          <span
            key={FUNNEL_STAGES[idx]?.name ?? idx}
            aria-hidden="true"
            className={cn(
              "h-[5px] flex-1 rounded-full",
              stageBarClasses[state],
            )}
          />
        ))}
      </div>
      <div className="mt-1.5 hidden gap-1 font-mono text-[9px] text-[#5e5878] [@media(min-width:480px)]:flex">
        {FUNNEL_STAGES.map((stage) => (
          <span
            key={stage.name}
            className={cn(
              "flex-1 truncate text-center",
              liveStageName === stage.name && "text-[#d8b4fe]",
            )}
          >
            {stage.label}
          </span>
        ))}
      </div>
    </div>
  );
}

interface NonFunnelStageBarProps {
  status: RunStatus;
}

function NonFunnelStageBar(props: NonFunnelStageBarProps): ReactElement {
  const { status } = props;
  const className =
    status === "succeeded"
      ? stageBarClasses.done
      : status === "failed"
        ? stageBarClasses.failed
        : status === "cancelled"
          ? stageBarClasses.dimmed
          : status === "running" || status === "paused"
            ? stageBarClasses.active
            : stageBarClasses.pending;
  return (
    <div className="mt-3">
      <span
        aria-hidden="true"
        className={cn("block h-[5px] w-full rounded-full", className)}
      />
    </div>
  );
}

function nonFunnelMetaLine(status: RunStatus, createdAt: string): string {
  const relative = formatRelativeTime(createdAt);
  if (status === "succeeded") {
    return `Succeeded · ${relative}`;
  }
  if (status === "failed") {
    return `Failed · ${relative}`;
  }
  if (status === "cancelled") {
    return `Cancelled · ${relative}`;
  }
  if (status === "running") {
    return `Running · ${relative}`;
  }
  return `${status} · ${relative}`;
}
