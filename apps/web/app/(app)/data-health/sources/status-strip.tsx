"use client";

import type { ReactElement } from "react";
import { StatusPill } from "@/components/ui";
import type { StatusPillStatus } from "@/components/ui";
import type {
  DataSourceEntry,
  TestPullResponse,
} from "@/lib/data-health/types";

export type PillState =
  | { readonly kind: "idle" }
  | { readonly kind: "loading" }
  | { readonly kind: "ok"; readonly count: number; readonly latencyMs: number }
  | { readonly kind: "error"; readonly detail: string };

export interface StatusStripProps {
  readonly enabledSources: ReadonlyArray<DataSourceEntry>;
  readonly results: ReadonlyMap<string, PillState>;
}

const STATUS_TO_PILL: Record<PillState["kind"], StatusPillStatus> = {
  idle: "pending",
  loading: "running",
  ok: "succeeded",
  error: "failed",
};

function pillLabel(state: PillState): string {
  switch (state.kind) {
    case "idle":
      return "idle";
    case "loading":
      return "...";
    case "ok":
      return `${state.count} · ${state.latencyMs}ms`;
    case "error":
      return "error";
  }
}

export function StatusStrip(props: StatusStripProps): ReactElement {
  return (
    <div
      className="sticky top-[64px] z-10 flex flex-wrap gap-2 border-y border-line bg-panel px-2 py-2"
      role="status"
      aria-label="Data source pulls"
    >
      {props.enabledSources.map((source) => {
        const state = props.results.get(source.key) ?? { kind: "idle" as const };
        return (
          <div
            key={source.key}
            className="flex items-center gap-1"
            title={source.label}
          >
            <span className="text-[11px] tracking-wide uppercase text-fg-muted">
              {source.key}
            </span>
            <StatusPill
              status={STATUS_TO_PILL[state.kind]}
              label={pillLabel(state)}
            />
          </div>
        );
      })}
    </div>
  );
}

export function responseToPillState(response: TestPullResponse): PillState {
  if (response.status === "ok") {
    return {
      kind: "ok",
      count: response.count,
      latencyMs: response.latency_ms,
    };
  }
  return { kind: "error", detail: response.error?.detail ?? "error" };
}
