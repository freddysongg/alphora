import type { ReactElement } from "react";

import { Card, CardContent, CardHeader, CardTitle, CapsLabel } from "@/components/ui";
import type { components } from "@/lib/api";

type SectorBriefPublic = components["schemas"]["SectorBriefPublic"];

const DIRECTION_TONE: Record<string, string> = {
  overweight: "text-success",
  underweight: "text-danger",
  neutral: "text-fg-subtle",
};

export interface SectorBriefCardProps {
  sectorBrief: SectorBriefPublic;
}

export function SectorBriefCard(props: SectorBriefCardProps): ReactElement {
  const { sectorBrief } = props;
  const { brief, judge } = sectorBrief;
  const directionTone = DIRECTION_TONE[brief.direction] ?? "text-fg";
  const convictionPct = Math.round(
    Math.max(0, Math.min(1, brief.confidence)) * 100,
  );

  return (
    <Card data-testid="sector-brief-card">
      <CardHeader>
        <CardTitle>{brief.sector_name}</CardTitle>
        <CapsLabel className={directionTone}>{brief.direction}</CapsLabel>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-2">
          <CapsLabel className="text-fg-subtle">CONVICTION</CapsLabel>
          <div
            role="progressbar"
            aria-label="conviction"
            aria-valuenow={convictionPct}
            aria-valuemin={0}
            aria-valuemax={100}
            className="h-1 flex-1 bg-surface-2 rounded-full overflow-hidden"
          >
            <div
              className="h-full bg-accent"
              style={{ width: `${convictionPct}%` }}
            />
          </div>
          <span className="font-mono text-xs text-fg tabular-nums">
            {convictionPct}%
          </span>
        </div>
        <div className="flex items-center gap-2">
          <CapsLabel className="text-fg-subtle">JUDGE</CapsLabel>
          <span className="font-mono text-xs text-fg">{judge.status}</span>
        </div>
        {brief.companies.length > 0 ? (
          <ul className="space-y-1" aria-label="company ideas">
            {brief.companies.map((company) => (
              <li
                key={`${company.name}:${company.ticker ?? "—"}`}
                className="flex items-center justify-between font-mono text-xs"
              >
                <span className="text-fg">{company.name}</span>
                <span className="text-fg-subtle">{company.ticker ?? "—"}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}
