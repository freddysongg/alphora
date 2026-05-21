"use client";

import type { ReactElement } from "react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CapsLabel,
  HexPill,
} from "@/components/ui";
import type { components } from "@/lib/api";

type HypothesisPublic = components["schemas"]["HypothesisPublic"];
type BeliefRecomputationPublic =
  components["schemas"]["BeliefRecomputationPublic"];
type BeliefInputBreakdown = components["schemas"]["BeliefInputBreakdown"];

export interface HypothesisBeliefBundle {
  hypothesis: HypothesisPublic;
  latest: BeliefRecomputationPublic | null;
}

export interface HypothesisBeliefExplainerProps {
  bundles: readonly HypothesisBeliefBundle[];
}

function formatBelief(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "—";
  }
  return value.toFixed(3);
}

function formatNumber(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  return value.toFixed(3);
}

function formatSign(value: number): string {
  return value >= 0 ? `+${value.toFixed(2)}` : value.toFixed(2);
}

function beliefTone(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "text-fg-subtle";
  }
  if (value >= 0.7) {
    return "text-accent-text";
  }
  if (value <= 0.3) {
    return "text-danger";
  }
  return "text-fg";
}

export function HypothesisBeliefExplainer(
  props: HypothesisBeliefExplainerProps,
): ReactElement {
  const { bundles } = props;
  if (bundles.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>BELIEF ENGINE</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-fg-subtle">
            No hypotheses proposed by this run.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>BELIEF ENGINE</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-6">
          {bundles.map((bundle) => (
            <li
              key={bundle.hypothesis.id}
              className="flex flex-col gap-3 border-t border-line/60 pt-4 first:border-t-0 first:pt-0"
            >
              <header className="flex items-center gap-3">
                <CapsLabel className="text-fg-subtle w-24 shrink-0">
                  {bundle.hypothesis.state}
                </CapsLabel>
                <p className="flex-1 min-w-0 text-sm text-fg">
                  {bundle.hypothesis.claim_text}
                </p>
                <HexPill value={bundle.hypothesis.id} />
                <span
                  className={`font-mono tabular-nums text-base ${beliefTone(
                    bundle.hypothesis.belief,
                  )}`}
                >
                  belief {formatBelief(bundle.hypothesis.belief)}
                </span>
              </header>
              <BeliefInputsTable latest={bundle.latest} />
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function BeliefInputsTable(props: {
  latest: BeliefRecomputationPublic | null;
}): ReactElement {
  const { latest } = props;
  if (latest === null) {
    return (
      <p className="text-xs text-fg-subtle">
        No belief has been computed yet. The engine will fire when a supporting
        or contradicting relation lands.
      </p>
    );
  }
  const inputs: readonly BeliefInputBreakdown[] = latest.inputs ?? [];
  if (inputs.length === 0) {
    return (
      <div className="flex flex-col gap-1 text-xs text-fg-subtle">
        <span>
          Computed at {new Date(latest.computed_at).toISOString()} via{" "}
          <span className="font-mono">{latest.computation_method}</span> — no
          relations have been linked yet, so the formula returned the neutral
          prior (0.5).
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-fg-subtle">
        Computed at {new Date(latest.computed_at).toISOString()} via{" "}
        <span className="font-mono">{latest.computation_method}</span> over{" "}
        {inputs.length} relation{inputs.length === 1 ? "" : "s"}.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono tabular-nums">
          <thead className="text-fg-subtle border-b border-line/60">
            <tr>
              <th className="text-left py-1 pr-3">type</th>
              <th className="text-right py-1 pr-3">sign</th>
              <th className="text-right py-1 pr-3">reliab.</th>
              <th className="text-right py-1 pr-3">conf.</th>
              <th className="text-right py-1 pr-3">relev.</th>
              <th className="text-right py-1 pr-3">decay</th>
              <th className="text-right py-1 pr-3">weight</th>
              <th className="text-right py-1">signed</th>
            </tr>
          </thead>
          <tbody>
            {inputs.map((input) => (
              <tr key={input.relation_id} className="border-b border-line/40">
                <td className="text-left py-1 pr-3 text-fg-muted">
                  {input.relation_type}
                </td>
                <td className="text-right py-1 pr-3 text-fg">
                  {formatSign(input.sign)}
                </td>
                <td className="text-right py-1 pr-3 text-fg-muted">
                  {formatNumber(input.reliability)}
                </td>
                <td className="text-right py-1 pr-3 text-fg-muted">
                  {formatNumber(input.confidence)}
                </td>
                <td className="text-right py-1 pr-3 text-fg-muted">
                  {formatNumber(input.relevance)}
                </td>
                <td className="text-right py-1 pr-3 text-fg-muted">
                  {formatNumber(input.decay)}
                </td>
                <td className="text-right py-1 pr-3 text-fg">
                  {formatNumber(input.weight)}
                </td>
                <td
                  className={`text-right py-1 ${
                    input.signed_contribution >= 0
                      ? "text-accent-text"
                      : "text-danger"
                  }`}
                >
                  {formatSign(input.signed_contribution)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
