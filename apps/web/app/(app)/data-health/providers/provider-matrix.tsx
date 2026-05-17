"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactElement } from "react";
import {
  StatusDot,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui";
import { useAppShellRail } from "@/components/shell/app-shell";
import type { components } from "@/lib/api";
import { providerCheckStatusToStatusKind } from "@/lib/data-health/status";
import { formatDateTime } from "@/lib/format/date-time";
import { ProviderCellRail } from "./provider-cell-rail";

type ProviderMatrixResponse = components["schemas"]["ProviderMatrix"];
type ProviderMatrixCell = components["schemas"]["ProviderMatrixCell"];

interface SelectedCell {
  provider: string;
  tool: string;
}

export interface ProviderMatrixProps {
  matrix: ProviderMatrixResponse;
}

function cellKey(provider: string, tool: string): string {
  return `${provider}::${tool}`;
}

function buildCellLookup(
  cells: readonly ProviderMatrixCell[],
): ReadonlyMap<string, ProviderMatrixCell> {
  const lookup = new Map<string, ProviderMatrixCell>();
  for (const cell of cells) {
    lookup.set(cellKey(cell.provider, cell.tool), cell);
  }
  return lookup;
}

function formatTooltip(cell: ProviderMatrixCell): string {
  return `${formatDateTime(cell.at)} · ${cell.sample_count.toLocaleString()} samples`;
}

export function ProviderMatrix(props: ProviderMatrixProps): ReactElement {
  const { matrix } = props;
  const [selected, setSelected] = useState<SelectedCell | null>(null);
  const { setRail, closeRail } = useAppShellRail();

  const cellLookup = useMemo(
    () => buildCellLookup(matrix.cells),
    [matrix.cells],
  );

  useEffect(() => {
    if (!selected) {
      return;
    }
    setRail({
      title: `${selected.provider} · ${selected.tool}`,
      body: (
        <ProviderCellRail
          provider={selected.provider}
          tool={selected.tool}
        />
      ),
    });
  }, [selected, setRail]);

  useEffect(() => {
    return () => {
      closeRail();
    };
  }, [closeRail]);

  return (
    <TooltipProvider delayDuration={300}>
      <div className="overflow-x-auto border border-line rounded-md">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line">
              <th
                scope="col"
                className="sticky left-0 z-10 bg-panel text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted py-2 px-3 text-left"
              >
                Provider
              </th>
              {matrix.tools.map((tool) => (
                <th
                  key={tool}
                  scope="col"
                  className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted py-2 px-3 text-center min-w-[120px]"
                >
                  {tool}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.providers.map((provider) => (
              <tr
                key={provider}
                className="border-b border-line/60 hover:bg-surface-2 transition-colors duration-150"
              >
                <th
                  scope="row"
                  className="sticky left-0 z-10 bg-panel text-sm text-fg py-3 px-3 text-left font-normal"
                >
                  {provider}
                </th>
                {matrix.tools.map((tool) => {
                  const cell = cellLookup.get(cellKey(provider, tool));
                  const isSelected =
                    selected !== null &&
                    selected.provider === provider &&
                    selected.tool === tool;
                  if (!cell) {
                    return (
                      <td key={tool} className="text-center py-3 px-3">
                        <span className="text-fg-subtle text-xs">—</span>
                      </td>
                    );
                  }
                  const statusKind = providerCheckStatusToStatusKind(cell.status);
                  return (
                    <td
                      key={tool}
                      className={`text-center py-3 px-3 cursor-pointer ${
                        isSelected ? "bg-surface-2" : ""
                      }`}
                      onClick={() => setSelected({ provider, tool })}
                    >
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span
                            className="inline-flex"
                            aria-label={`${provider} ${tool} ${cell.status}`}
                          >
                            <StatusDot
                              status={statusKind}
                              label={cell.status}
                              className="[&>span:last-child]:sr-only"
                            />
                          </span>
                        </TooltipTrigger>
                        <TooltipContent>{formatTooltip(cell)}</TooltipContent>
                      </Tooltip>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </TooltipProvider>
  );
}
