"use client";

import type { ReactElement } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui";
import type { components } from "@/lib/api";

type RunEvidenceFlow = components["schemas"]["RunEvidenceFlow"];
type EvidenceFlowSourceRow =
  components["schemas"]["EvidenceFlowSourceRow"];

export interface EvidenceFlowProps {
  flow: RunEvidenceFlow | null;
}

function formatReliability(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return `${(value * 100).toFixed(0)}%`;
}

function reliabilityClass(value: number | null): string {
  if (value === null) {
    return "text-fg-subtle";
  }
  if (value >= 0.85) {
    return "text-accent-text";
  }
  if (value <= 0.5) {
    return "text-danger";
  }
  return "text-fg";
}

export function EvidenceFlow(props: EvidenceFlowProps): ReactElement {
  const { flow } = props;
  if (flow === null || flow.sources.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>EVIDENCE FLOW</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-fg-subtle">
            No evidence has flowed into this run yet.
          </p>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>EVIDENCE FLOW</CardTitle>
      </CardHeader>
      <CardContent>
        <div
          className="grid grid-cols-3 gap-6 mb-6"
          data-testid="evidence-flow-totals"
        >
          <SummaryStat label="EVIDENCE" value={flow.total_evidence.toLocaleString()} />
          <SummaryStat
            label="CHUNK CITATIONS"
            value={flow.total_chunk_citations.toLocaleString()}
          />
          <SummaryStat
            label="HYPOTHESES"
            value={flow.total_hypotheses.toLocaleString()}
          />
        </div>
        <div className="border-t border-line pt-4">
          <table className="w-full text-sm" data-testid="evidence-flow-table">
            <thead>
              <tr className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
                <th className="text-left py-2">SOURCE</th>
                <th className="text-left py-2">KIND</th>
                <th className="text-right py-2">EVIDENCE</th>
                <th className="text-right py-2">CITATIONS</th>
                <th className="text-right py-2">HYPOTHESES</th>
                <th className="text-right py-2">RELIABILITY</th>
              </tr>
            </thead>
            <tbody>
              {flow.sources.map((row) => (
                <SourceRow key={`${row.source_name}-${row.source_id ?? "none"}`} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

interface SourceRowProps {
  row: EvidenceFlowSourceRow;
}

function SourceRow(props: SourceRowProps): ReactElement {
  const { row } = props;
  return (
    <tr className="border-t border-line/40 font-mono tabular-nums text-fg">
      <td className="py-2">{row.source_name}</td>
      <td className="py-2 text-fg-muted">{row.source_kind ?? "—"}</td>
      <td className="text-right py-2">{row.evidence_count.toLocaleString()}</td>
      <td className="text-right py-2">{row.chunk_citation_count.toLocaleString()}</td>
      <td className="text-right py-2">{row.hypothesis_count.toLocaleString()}</td>
      <td
        className={`text-right py-2 ${reliabilityClass(row.reliability_score)}`}
      >
        {formatReliability(row.reliability_score)}
      </td>
    </tr>
  );
}

interface SummaryStatProps {
  label: string;
  value: string;
}

function SummaryStat(props: SummaryStatProps): ReactElement {
  const { label, value } = props;
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
        {label}
      </span>
      <span className="text-2xl font-mono tabular-nums text-fg">{value}</span>
    </div>
  );
}
