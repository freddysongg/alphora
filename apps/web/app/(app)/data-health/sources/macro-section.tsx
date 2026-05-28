"use client";

import type { ReactElement } from "react";
import { Button } from "@/components/ui";
import type {
  DataSourceEntry,
  TestPullResponse,
} from "@/lib/data-health/types";
import { SourceRow } from "./source-row";

export interface MacroSectionProps {
  readonly sources: ReadonlyArray<DataSourceEntry>;
  readonly results: ReadonlyMap<string, TestPullResponse>;
  readonly errors: ReadonlyMap<string, string>;
  readonly loadingKeys: ReadonlySet<string>;
  readonly onPull: (entry: DataSourceEntry) => void;
  readonly onPullAll: () => void;
  readonly onSettingsUpdated: (updated: DataSourceEntry) => void;
}

export function MacroSection(props: MacroSectionProps): ReactElement {
  return (
    <section
      className="flex flex-col gap-3 mt-8"
      aria-labelledby="macro-heading"
    >
      <div className="flex items-center justify-between">
        <h2 id="macro-heading" className="text-sm font-medium text-fg">
          Macro / event sources
        </h2>
        <Button variant="secondary" size="sm" onClick={props.onPullAll}>
          Pull All Macro
        </Button>
      </div>
      <div className="flex flex-col gap-2">
        {props.sources.map((entry) => (
          <SourceRow
            key={entry.key}
            entry={entry}
            ticker=""
            result={props.results.get(entry.key) ?? null}
            errorDetail={props.errors.get(entry.key) ?? null}
            isLoading={props.loadingKeys.has(entry.key)}
            onPull={props.onPull}
            onSettingsUpdated={props.onSettingsUpdated}
          />
        ))}
      </div>
    </section>
  );
}
