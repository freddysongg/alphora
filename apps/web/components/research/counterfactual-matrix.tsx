"use client";

import type { ReactElement } from "react";
import { useMemo } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui";
import type { components } from "@/lib/api";

type CounterfactualPerturbation =
  components["schemas"]["CounterfactualPerturbationPublic"];
type BriefKind = components["schemas"]["BriefKindEnum"];
type PerturbationKind = components["schemas"]["PerturbationKindEnum"];

export interface CounterfactualMatrixProps {
  perturbations: readonly CounterfactualPerturbation[];
}

interface MatrixRow {
  briefKind: BriefKind;
  briefId: string | null;
  cells: Map<PerturbationKind, CounterfactualPerturbation>;
}

const PERTURBATION_ORDER: readonly PerturbationKind[] = [
  "drop_top_evidence",
  "flip_top_call_direction",
  "redact_top_quote",
  "lower_top_call_conviction",
  "swap_call_ordering",
];

const PERTURBATION_LABEL: Record<PerturbationKind, string> = {
  drop_top_evidence: "DROP TOP EV",
  flip_top_call_direction: "FLIP DIRN",
  redact_top_quote: "REDACT QUOTE",
  lower_top_call_conviction: "LOWER CONV",
  swap_call_ordering: "SWAP ORDER",
};

const BRIEF_KIND_LABEL: Record<BriefKind, string> = {
  macro: "MACRO",
  sector: "SECTOR",
  company: "COMPANY",
  portfolio: "PORTFOLIO",
};

function groupByBrief(
  perturbations: readonly CounterfactualPerturbation[],
): MatrixRow[] {
  const grouped = new Map<string, MatrixRow>();
  for (const row of perturbations) {
    const key = `${row.brief_kind}:${row.brief_id ?? "none"}`;
    let bucket = grouped.get(key);
    if (bucket === undefined) {
      bucket = {
        briefKind: row.brief_kind,
        briefId: row.brief_id ?? null,
        cells: new Map(),
      };
      grouped.set(key, bucket);
    }
    bucket.cells.set(row.perturbation_kind, row);
  }
  const ordered = Array.from(grouped.values()).sort((a, b) => {
    if (a.briefKind !== b.briefKind) {
      return a.briefKind.localeCompare(b.briefKind);
    }
    return (a.briefId ?? "").localeCompare(b.briefId ?? "");
  });
  return ordered;
}

function cellClass(cell: CounterfactualPerturbation | undefined): string {
  if (cell === undefined) {
    return "bg-transparent text-fg-subtle";
  }
  if (!cell.is_meaningful) {
    return "bg-line/40 text-fg-subtle";
  }
  if (cell.decision_changed) {
    return "bg-danger/30 text-danger";
  }
  return "bg-success/20 text-success";
}

function cellLabel(cell: CounterfactualPerturbation | undefined): string {
  if (cell === undefined) {
    return "—";
  }
  if (!cell.is_meaningful) {
    return "no-op";
  }
  return cell.decision_changed ? "changed" : "stable";
}

function cellTitle(cell: CounterfactualPerturbation | undefined): string {
  if (cell === undefined) {
    return "no perturbation recorded";
  }
  const delta = JSON.stringify(cell.decision_delta);
  return `${cellLabel(cell)} · delta=${delta}`;
}

export function CounterfactualMatrix(
  props: CounterfactualMatrixProps,
): ReactElement {
  const { perturbations } = props;
  const rows = useMemo(() => groupByBrief(perturbations), [perturbations]);
  if (rows.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>COUNTERFACTUAL MATRIX</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-fg-subtle">
            No counterfactual perturbations recorded for this run yet.
          </p>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>COUNTERFACTUAL MATRIX</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table
            className="w-full text-sm font-mono tabular-nums"
            data-testid="counterfactual-matrix"
          >
            <thead>
              <tr className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
                <th className="text-left py-2 pr-4">BRIEF</th>
                {PERTURBATION_ORDER.map((kind) => (
                  <th key={kind} className="text-center py-2 px-2">
                    {PERTURBATION_LABEL[kind]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={`${row.briefKind}:${row.briefId ?? "none"}`}
                  className="border-t border-line/40 text-fg"
                  data-testid="counterfactual-matrix-row"
                >
                  <td className="py-2 pr-4">
                    <span className="text-fg-muted">
                      {BRIEF_KIND_LABEL[row.briefKind]}
                    </span>
                    {row.briefId !== null ? (
                      <span className="ml-2 text-fg-subtle text-xs">
                        {row.briefId.slice(0, 8)}
                      </span>
                    ) : null}
                  </td>
                  {PERTURBATION_ORDER.map((kind) => {
                    const cell = row.cells.get(kind);
                    return (
                      <td
                        key={kind}
                        className={`text-center py-2 px-2 ${cellClass(cell)}`}
                        title={cellTitle(cell)}
                        data-testid="counterfactual-matrix-cell"
                        data-cell-state={cell === undefined ? "missing" : cell.is_meaningful ? (cell.decision_changed ? "changed" : "stable") : "no-op"}
                      >
                        {cellLabel(cell)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
