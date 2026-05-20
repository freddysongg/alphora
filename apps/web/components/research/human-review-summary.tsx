"use client";

import type { ReactElement } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui";
import type { components } from "@/lib/api";

type HumanReviewSummary = components["schemas"]["HumanReviewSummary"];

export interface HumanReviewSummaryWidgetProps {
  summary: HumanReviewSummary;
}

function formatMean(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  return value.toFixed(2);
}

export function HumanReviewSummaryWidget(
  props: HumanReviewSummaryWidgetProps,
): ReactElement {
  const { summary } = props;
  if (summary.weeks.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>HUMAN REVIEW SUMMARY</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-fg-subtle">No weekly reviews yet.</p>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>HUMAN REVIEW SUMMARY</CardTitle>
      </CardHeader>
      <CardContent>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
              <th className="py-2 pr-4">Week</th>
              <th className="py-2 pr-4 text-right">Reviews</th>
              <th className="py-2 pr-4 text-right">Mean surfaced</th>
              <th className="py-2 text-right">Mean missed</th>
            </tr>
          </thead>
          <tbody>
            {summary.weeks.map((week) => (
              <tr key={week.week_start} className="border-t border-line/60">
                <td className="py-2 pr-4 font-mono tabular-nums text-fg">
                  {week.week_start}
                </td>
                <td className="py-2 pr-4 text-right font-mono tabular-nums text-fg-muted">
                  {week.review_count}
                </td>
                <td className="py-2 pr-4 text-right font-mono tabular-nums text-fg">
                  {formatMean(week.mean_surfaced_missed)}
                </td>
                <td className="py-2 text-right font-mono tabular-nums text-fg">
                  {formatMean(week.mean_missed_noticed)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
