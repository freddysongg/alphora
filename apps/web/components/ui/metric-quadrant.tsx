import type { ReactElement } from "react";
import { Sparkline } from "@/components/ui/sparkline";
import { CapsLabel } from "@/components/ui/caps-label";
import { chartAlphas } from "@/lib/tokens";
import { cn } from "@/lib/cn";

export interface MetricTile {
  label: string;
  value: string;
  sparkline?: number[];
}

export interface MetricQuadrantProps {
  tiles: MetricTile[];
  className?: string;
}

const dotGridBackground = `radial-gradient(${chartAlphas.gridDot} 1px, transparent 1px)`;

export function MetricQuadrant(props: MetricQuadrantProps): ReactElement {
  const { tiles, className } = props;
  return (
    <div
      className={cn(
        "grid grid-cols-2 bg-surface border border-line rounded-xl divide-x divide-y divide-line overflow-hidden",
        className,
      )}
    >
      {tiles.map((tile, index) => (
        <MetricTileCell key={`${tile.label}-${index}`} tile={tile} />
      ))}
    </div>
  );
}

interface MetricTileCellProps {
  tile: MetricTile;
}

function MetricTileCell(props: MetricTileCellProps): ReactElement {
  const { tile } = props;
  return (
    <div className="relative flex flex-col p-4 min-h-[120px]">
      <div className="flex items-start justify-between gap-4">
        <CapsLabel>{tile.label}</CapsLabel>
        <span className="text-2xl font-mono tabular-nums text-fg leading-none">
          {tile.value}
        </span>
      </div>
      {tile.sparkline && tile.sparkline.length > 0 ? (
        <div
          className="mt-auto h-[60%] -mx-2"
          style={{
            backgroundImage: dotGridBackground,
            backgroundSize: "16px 16px",
            backgroundPosition: "0 0",
          }}
        >
          <Sparkline data={tile.sparkline} height={48} width="100%" />
        </div>
      ) : null}
    </div>
  );
}
