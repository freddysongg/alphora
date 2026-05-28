"use client";

import { useState } from "react";
import type { ReactElement } from "react";
import { CodeBlock } from "@/components/ui";
import type { TestPullResponse } from "@/lib/data-health/types";
import { PREVIEW_COLUMNS } from "./preview-columns";

export interface ResultPanelProps {
  readonly sourceKey: string;
  readonly response: TestPullResponse;
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

export function ResultPanel(props: ResultPanelProps): ReactElement {
  const [showRaw, setShowRaw] = useState<boolean>(false);
  const columns = PREVIEW_COLUMNS.get(props.sourceKey) ?? [];

  if (props.response.status === "error") {
    return (
      <div
        role="alert"
        className="rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
      >
        {props.response.error?.detail ?? "Unknown error"}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto border border-line rounded-md">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line">
              {columns.map((col) => (
                <th
                  key={col.key}
                  scope="col"
                  className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted py-2 px-3 text-left"
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {props.response.preview.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-b border-line/60">
                {columns.map((col) => (
                  <td key={col.key} className="py-2 px-3 text-fg">
                    {formatCell((row as Record<string, unknown>)[col.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        className="self-start text-xs text-fg-muted underline"
        onClick={() => setShowRaw((prev) => !prev)}
      >
        {showRaw ? "Hide raw JSON" : "View raw JSON"}
      </button>
      {showRaw ? (
        <CodeBlock lang="json">{props.response.raw ?? "null"}</CodeBlock>
      ) : null}
    </div>
  );
}
