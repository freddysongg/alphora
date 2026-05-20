"use client";

import type { ReactElement } from "react";

import { Card, CardContent, CardHeader, CardTitle, StatusDot } from "@/components/ui";
import type { components } from "@/lib/api";

type GateRow = components["schemas"]["CounterfactualGateRunPublic"];
type BriefKind = components["schemas"]["BriefKindEnum"];

export interface CounterfactualGateSummaryProps {
  gates: readonly GateRow[];
}

const briefKindLabel: Record<BriefKind, string> = {
  macro: "MACRO",
  sector: "SECTOR",
  company: "COMPANY",
  portfolio: "PORTFOLIO",
};

function formatPercent(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(0)}%`;
}

export function CounterfactualGateSummary(
  props: CounterfactualGateSummaryProps,
): ReactElement {
  const { gates } = props;
  if (gates.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>COUNTERFACTUAL GATE</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-fg-subtle">
            No counterfactual perturbations recorded for this run yet.
          </p>
        </CardContent>
      </Card>
    );
  }

  const ordered = [...gates].sort((a, b) =>
    a.created_at.localeCompare(b.created_at),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>COUNTERFACTUAL GATE</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-3">
          {ordered.map((gate) => (
            <li
              key={gate.id}
              className="flex items-center gap-4 text-sm text-fg"
            >
              <StatusDot
                status={gate.passed ? "succeeded" : "failed"}
                label={briefKindLabel[gate.brief_kind]}
              />
              <span className="font-mono tabular-nums text-fg-muted">
                {gate.meaningful_changed_count}/{gate.meaningful_count} meaningful
                changed
              </span>
              <span
                className={
                  gate.passed
                    ? "font-mono tabular-nums text-fg"
                    : "font-mono tabular-nums text-danger"
                }
              >
                {formatPercent(gate.change_rate)}
              </span>
              <span className="font-mono tabular-nums text-fg-subtle">
                threshold {formatPercent(gate.threshold)}
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
