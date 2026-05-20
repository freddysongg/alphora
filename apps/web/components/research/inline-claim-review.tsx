"use client";

import type { ReactElement } from "react";
import { useState } from "react";

import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui";
import { getBrowserApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";

type BriefKind = components["schemas"]["BriefKindEnum"];
type HumanReviewInput = components["schemas"]["HumanReviewInput"];

export interface InlineClaim {
  chunkId: string;
  quote: string;
  briefKind: BriefKind;
  briefId: string | null;
  source: string | null;
}

export interface InlineClaimReviewProps {
  runId: string;
  defaultWeekStart: string;
  reviewer: string;
  claims: readonly InlineClaim[];
  onSubmitted?: () => void;
}

interface RowState {
  surfacedMissed: number;
  missedNoticed: number;
  status: "idle" | "saving" | "saved" | "error";
  errorMessage: string | null;
}

const INITIAL_ROW_STATE: RowState = {
  surfacedMissed: 0,
  missedNoticed: 0,
  status: "idle",
  errorMessage: null,
};

const AXIS_LEVELS: readonly number[] = [-2, -1, 0, 1, 2];

function levelToneClass(level: number): string {
  if (level > 0) return "text-accent-text";
  if (level < 0) return "text-danger";
  return "text-fg-muted";
}

function levelLabel(level: number): string {
  if (level > 0) return `+${level}`;
  return level.toString();
}

export function InlineClaimReview(
  props: InlineClaimReviewProps,
): ReactElement {
  const { runId, defaultWeekStart, reviewer, claims, onSubmitted } = props;
  const [byClaim, setByClaim] = useState<Record<string, RowState>>({});

  if (claims.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>INLINE CLAIM REVIEW</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-fg-subtle">
            No cited claims to review for this run.
          </p>
        </CardContent>
      </Card>
    );
  }

  const updateRow = (chunkId: string, patch: Partial<RowState>): void => {
    setByClaim((prev) => {
      const current = prev[chunkId] ?? INITIAL_ROW_STATE;
      return { ...prev, [chunkId]: { ...current, ...patch } };
    });
  };

  const handleSubmit = async (
    claim: InlineClaim,
  ): Promise<void> => {
    const current = byClaim[claim.chunkId] ?? INITIAL_ROW_STATE;
    if (current.status === "saving") {
      return;
    }
    if (reviewer.trim() === "") {
      updateRow(claim.chunkId, {
        status: "error",
        errorMessage: "Reviewer name is required.",
      });
      return;
    }
    updateRow(claim.chunkId, { status: "saving", errorMessage: null });
    const payload: HumanReviewInput = {
      run_id: runId,
      brief_kind: claim.briefKind,
      week_start: defaultWeekStart,
      reviewer: reviewer.trim(),
      surfaced_missed: current.surfacedMissed,
      missed_noticed: current.missedNoticed,
      notes: `chunk_id=${claim.chunkId}${
        claim.briefId !== null ? ` brief_id=${claim.briefId}` : ""
      }`,
    };
    try {
      const response = await getBrowserApi().POST("/api/human-reviews", {
        body: payload,
      });
      const created = response.data;
      if (created === undefined) {
        updateRow(claim.chunkId, {
          status: "error",
          errorMessage: "Backend returned an empty response.",
        });
        return;
      }
      updateRow(claim.chunkId, { status: "saved", errorMessage: null });
      onSubmitted?.();
    } catch (caught) {
      if (isApiError(caught)) {
        updateRow(claim.chunkId, {
          status: "error",
          errorMessage: caught.detail,
        });
        return;
      }
      updateRow(claim.chunkId, {
        status: "error",
        errorMessage: "Unable to save review.",
      });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>INLINE CLAIM REVIEW</CardTitle>
      </CardHeader>
      <CardContent>
        <ul
          className="flex flex-col gap-4"
          data-testid="inline-claim-review-list"
        >
          {claims.map((claim) => {
            const state = byClaim[claim.chunkId] ?? INITIAL_ROW_STATE;
            return (
              <li
                key={claim.chunkId}
                className="border border-line/40 rounded-md p-4 flex flex-col gap-3 bg-surface/40"
                data-testid="inline-claim-review-row"
              >
                <div className="flex items-baseline justify-between gap-4">
                  <p className="text-sm text-fg flex-1 leading-relaxed">
                    {claim.quote}
                  </p>
                  <span className="text-[11px] tracking-[0.14em] uppercase text-fg-muted whitespace-nowrap">
                    {claim.briefKind}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-[11px] tracking-[0.14em] uppercase text-fg-subtle font-mono">
                  <span>CHUNK {claim.chunkId.slice(0, 8)}</span>
                  {claim.source !== null ? (
                    <span className="text-fg-muted">SOURCE {claim.source}</span>
                  ) : null}
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <AxisGroup
                    label="SURFACED MISSED"
                    value={state.surfacedMissed}
                    onChange={(next) =>
                      updateRow(claim.chunkId, { surfacedMissed: next })
                    }
                    testId={`surfaced-${claim.chunkId}`}
                  />
                  <AxisGroup
                    label="MISSED NOTICED"
                    value={state.missedNoticed}
                    onChange={(next) =>
                      updateRow(claim.chunkId, { missedNoticed: next })
                    }
                    testId={`missed-${claim.chunkId}`}
                  />
                </div>
                <div className="flex items-center justify-between">
                  {state.status === "error" && state.errorMessage !== null ? (
                    <p className="text-xs text-danger" role="alert">
                      {state.errorMessage}
                    </p>
                  ) : state.status === "saved" ? (
                    <p className="text-xs text-accent-text">Saved</p>
                  ) : (
                    <span className="text-xs text-fg-subtle">—</span>
                  )}
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => {
                      void handleSubmit(claim);
                    }}
                    disabled={state.status === "saving"}
                    data-testid={`inline-claim-review-save-${claim.chunkId}`}
                  >
                    {state.status === "saving" ? "Saving…" : "Save"}
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

interface AxisGroupProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  testId: string;
}

function AxisGroup(props: AxisGroupProps): ReactElement {
  const { label, value, onChange, testId } = props;
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
        {label}
      </span>
      <div className="flex gap-1" data-testid={testId}>
        {AXIS_LEVELS.map((level) => {
          const selected = value === level;
          const base =
            "px-2 py-1 text-xs font-mono tabular-nums border rounded-sm";
          const toneClass = levelToneClass(level);
          const stateClass = selected
            ? "border-accent bg-surface-2"
            : "border-line/60 hover:border-line";
          return (
            <button
              key={level}
              type="button"
              onClick={() => onChange(level)}
              className={`${base} ${toneClass} ${stateClass}`}
              data-axis-level={level}
              aria-pressed={selected}
            >
              {levelLabel(level)}
            </button>
          );
        })}
      </div>
    </div>
  );
}
