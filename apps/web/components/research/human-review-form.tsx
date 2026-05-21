"use client";

import { useState } from "react";
import type { FormEvent, ReactElement } from "react";

import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
} from "@/components/ui";
import { getBrowserApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";

type HumanReviewInput = components["schemas"]["HumanReviewInput"];
type BriefKind = components["schemas"]["BriefKindEnum"];

const AXIS_LEVELS: readonly number[] = [-2, -1, 0, 1, 2];
const BRIEF_KIND_OPTIONS: readonly BriefKind[] = [
  "macro",
  "sector",
  "company",
  "portfolio",
];

export interface HumanReviewFormProps {
  runId?: string;
  defaultWeekStart: string;
  onSubmitted?: () => void;
}

interface FormState {
  reviewer: string;
  weekStart: string;
  briefKind: BriefKind | "";
  surfacedMissed: number;
  missedNoticed: number;
  notes: string;
}

function makeInitialState(defaultWeekStart: string): FormState {
  return {
    reviewer: "",
    weekStart: defaultWeekStart,
    briefKind: "",
    surfacedMissed: 0,
    missedNoticed: 0,
    notes: "",
  };
}

function describeSurfaced(level: number): string {
  if (level === 2) return "+2 surfaced a lot I'd have missed";
  if (level === 1) return "+1 surfaced something I'd have missed";
  if (level === 0) return "0 no new surfacing";
  if (level === -1) return "-1 surfaced noise";
  return "-2 surfaced misleading";
}

function describeMissed(level: number): string {
  if (level === 2) return "+2 missed a lot I noticed";
  if (level === 1) return "+1 missed something I noticed";
  if (level === 0) return "0 nothing I noticed was missed";
  if (level === -1) return "-1 covered what I noticed";
  return "-2 covered more than I noticed";
}

export function HumanReviewForm(props: HumanReviewFormProps): ReactElement {
  const { runId, defaultWeekStart, onSubmitted } = props;
  const [state, setState] = useState<FormState>(() =>
    makeInitialState(defaultWeekStart),
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submittedAt, setSubmittedAt] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (submitting) {
      return;
    }
    setError(null);
    setSubmitting(true);
    const payload: HumanReviewInput = {
      week_start: state.weekStart,
      reviewer: state.reviewer.trim(),
      surfaced_missed: state.surfacedMissed,
      missed_noticed: state.missedNoticed,
      notes: state.notes.trim() === "" ? null : state.notes.trim(),
      brief_kind: state.briefKind === "" ? null : state.briefKind,
      run_id: runId ?? null,
    };
    try {
      const response = await getBrowserApi().POST("/api/human-reviews", {
        body: payload,
      });
      const created = response.data;
      if (created === undefined) {
        setError("Backend returned an empty response.");
        return;
      }
      setSubmittedAt(created.created_at);
      setState(makeInitialState(defaultWeekStart));
      onSubmitted?.();
    } catch (caught) {
      if (isApiError(caught)) {
        setError(caught.detail);
        return;
      }
      setError("Unable to save review.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>HUMAN REVIEW</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-4"
          aria-label="Human review form"
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <label className="flex flex-col gap-1 text-sm text-fg-muted">
              <span className="text-[11px] tracking-[0.14em] font-medium uppercase">
                Reviewer
              </span>
              <Input
                type="text"
                required
                value={state.reviewer}
                onChange={(event) =>
                  setState((prev) => ({ ...prev, reviewer: event.target.value }))
                }
                placeholder="e.g. alice"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-fg-muted">
              <span className="text-[11px] tracking-[0.14em] font-medium uppercase">
                Week start
              </span>
              <Input
                type="date"
                required
                value={state.weekStart}
                onChange={(event) =>
                  setState((prev) => ({ ...prev, weekStart: event.target.value }))
                }
              />
            </label>
          </div>

          <fieldset className="flex flex-col gap-2">
            <legend className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
              Surfaced something I&apos;d have missed
            </legend>
            <div className="flex flex-wrap gap-2">
              {AXIS_LEVELS.map((level) => (
                <label
                  key={`surfaced-${level}`}
                  className="flex items-center gap-2 text-xs font-mono tabular-nums text-fg"
                >
                  <input
                    type="radio"
                    name="surfaced_missed"
                    value={level}
                    checked={state.surfacedMissed === level}
                    onChange={() =>
                      setState((prev) => ({ ...prev, surfacedMissed: level }))
                    }
                  />
                  <span>{describeSurfaced(level)}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="flex flex-col gap-2">
            <legend className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
              Missed something I noticed
            </legend>
            <div className="flex flex-wrap gap-2">
              {AXIS_LEVELS.map((level) => (
                <label
                  key={`missed-${level}`}
                  className="flex items-center gap-2 text-xs font-mono tabular-nums text-fg"
                >
                  <input
                    type="radio"
                    name="missed_noticed"
                    value={level}
                    checked={state.missedNoticed === level}
                    onChange={() =>
                      setState((prev) => ({ ...prev, missedNoticed: level }))
                    }
                  />
                  <span>{describeMissed(level)}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <label className="flex flex-col gap-1 text-sm text-fg-muted">
            <span className="text-[11px] tracking-[0.14em] font-medium uppercase">
              Brief kind (optional)
            </span>
            <select
              value={state.briefKind}
              onChange={(event) =>
                setState((prev) => ({
                  ...prev,
                  briefKind: event.target.value as BriefKind | "",
                }))
              }
              className="h-9 w-full rounded-md bg-surface border border-line px-3 text-sm text-fg focus:border-line-strong focus:bg-surface-2 focus:outline-none transition-[background-color,border-color] duration-150"
            >
              <option value="">— any —</option>
              {BRIEF_KIND_OPTIONS.map((kind) => (
                <option key={kind} value={kind}>
                  {kind}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-sm text-fg-muted">
            <span className="text-[11px] tracking-[0.14em] font-medium uppercase">
              Notes
            </span>
            <textarea
              value={state.notes}
              onChange={(event) =>
                setState((prev) => ({ ...prev, notes: event.target.value }))
              }
              rows={3}
              maxLength={4000}
              className="w-full rounded-md bg-surface border border-line px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:border-line-strong focus:bg-surface-2 focus:outline-none transition-[background-color,border-color] duration-150"
            />
          </label>

          {error !== null ? (
            <p className="text-sm text-danger" role="alert">
              {error}
            </p>
          ) : null}
          {submittedAt !== null && error === null ? (
            <p className="text-sm text-accent-text">
              Saved at {new Date(submittedAt).toLocaleString()}
            </p>
          ) : null}

          <div className="flex justify-end">
            <Button type="submit" disabled={submitting}>
              {submitting ? "Saving…" : "Save review"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
