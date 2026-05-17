"use client";

import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import {
  StatusDot,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui";
import { useAppShellRail } from "@/components/shell/app-shell";
import {
  providerMatrix,
  providerRows,
  toolColumns,
} from "@/lib/fixtures/providers";
import type {
  MatrixCell,
  ProviderId,
  ToolId,
} from "@/lib/fixtures/providers";
import { ProviderCellRail } from "./provider-cell-rail";

interface SelectedCell {
  providerId: ProviderId;
  toolId: ToolId;
}

function formatTooltip(cell: MatrixCell): string {
  return `${cell.lastFetch} · ${cell.samples.toLocaleString()} samples`;
}

export function ProviderMatrix(): ReactElement {
  const [selected, setSelected] = useState<SelectedCell | null>(null);
  const { setRail, closeRail } = useAppShellRail();

  useEffect(() => {
    if (!selected) {
      return;
    }
    const providerRow = providerRows.find((row) => row.id === selected.providerId);
    const toolColumn = toolColumns.find((column) => column.id === selected.toolId);
    if (!providerRow || !toolColumn) {
      return;
    }
    setRail({
      title: `${providerRow.label} · ${toolColumn.label}`,
      body: (
        <ProviderCellRail
          providerLabel={providerRow.label}
          toolLabel={toolColumn.label}
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
              {toolColumns.map((column) => (
                <th
                  key={column.id}
                  scope="col"
                  className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted py-2 px-3 text-center min-w-[120px]"
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {providerRows.map((providerRow) => (
              <tr
                key={providerRow.id}
                className="border-b border-line/60 hover:bg-surface-2 transition-colors duration-150"
              >
                <th
                  scope="row"
                  className="sticky left-0 z-10 bg-panel text-sm text-fg py-3 px-3 text-left font-normal"
                >
                  {providerRow.label}
                </th>
                {toolColumns.map((column) => {
                  const cell = providerMatrix[providerRow.id][column.id];
                  const isSelected =
                    selected !== null &&
                    selected.providerId === providerRow.id &&
                    selected.toolId === column.id;
                  if (!cell) {
                    return (
                      <td key={column.id} className="text-center py-3 px-3">
                        <span className="text-fg-subtle text-xs">—</span>
                      </td>
                    );
                  }
                  return (
                    <td
                      key={column.id}
                      className={`text-center py-3 px-3 cursor-pointer ${
                        isSelected ? "bg-surface-2" : ""
                      }`}
                      onClick={() =>
                        setSelected({
                          providerId: providerRow.id,
                          toolId: column.id,
                        })
                      }
                    >
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span
                            className="inline-flex"
                            aria-label={`${providerRow.label} ${column.label} ${cell.status}`}
                          >
                            <StatusDot
                              status={cell.status}
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
