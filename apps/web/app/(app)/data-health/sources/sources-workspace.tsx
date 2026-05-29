"use client";

import { useMemo, useRef, useState } from "react";
import type { ReactElement } from "react";
import { Button, Input } from "@/components/ui";
import type {
  DataSourceEntry,
  TestPullResponse,
} from "@/lib/data-health/types";
import { groupSourcesByProvider } from "@/lib/data-health/types";
import { pullOne } from "@/lib/data-health/test-pull-client";
import { MacroSection } from "./macro-section";
import { SourceRow } from "./source-row";
import { StatusStrip, responseToPillState } from "./status-strip";
import type { PillState } from "./status-strip";

export interface SourcesWorkspaceProps {
  readonly initialSources: ReadonlyArray<DataSourceEntry>;
}

interface PullState {
  readonly responses: ReadonlyMap<string, TestPullResponse>;
  readonly errors: ReadonlyMap<string, string>;
  readonly loading: ReadonlySet<string>;
}

function buildPillStates(
  enabled: ReadonlyArray<DataSourceEntry>,
  state: PullState,
): ReadonlyMap<string, PillState> {
  const out: Map<string, PillState> = new Map();
  for (const source of enabled) {
    if (state.loading.has(source.key)) {
      out.set(source.key, { kind: "loading" });
      continue;
    }
    const response = state.responses.get(source.key);
    if (response !== undefined) {
      out.set(source.key, responseToPillState(response));
      continue;
    }
    const error = state.errors.get(source.key);
    if (error !== undefined) {
      out.set(source.key, { kind: "error", detail: error });
      continue;
    }
    out.set(source.key, { kind: "idle" });
  }
  return out;
}

export function SourcesWorkspace(
  props: SourcesWorkspaceProps,
): ReactElement {
  const [sources, setSources] = useState<ReadonlyArray<DataSourceEntry>>(
    props.initialSources,
  );
  const [ticker, setTicker] = useState<string>("");
  const [state, setState] = useState<PullState>({
    responses: new Map(),
    errors: new Map(),
    loading: new Set(),
  });
  const abortControllerRef = useRef<AbortController>(new AbortController());

  const tickerSources = useMemo(
    () => sources.filter((s) => s.scope === "ticker"),
    [sources],
  );
  const macroSources = useMemo(
    () => sources.filter((s) => s.scope === "macro"),
    [sources],
  );
  const enabledTickerSources = useMemo(
    () => tickerSources.filter((s) => s.settings.enabled),
    [tickerSources],
  );
  const enabledCount = sources.filter((s) => s.settings.enabled).length;
  const disabledCount = sources.length - enabledCount;
  const providerGroups = useMemo(
    () => groupSourcesByProvider(tickerSources),
    [tickerSources],
  );
  const pillStates = useMemo(
    () => buildPillStates(enabledTickerSources, state),
    [enabledTickerSources, state],
  );

  function markLoading(key: string): void {
    setState((prev) => {
      const loading = new Set(prev.loading);
      loading.add(key);
      const responses = new Map(prev.responses);
      responses.delete(key);
      const errors = new Map(prev.errors);
      errors.delete(key);
      return { loading, responses, errors };
    });
  }

  function recordResult(
    key: string,
    response: TestPullResponse | null,
    errorDetail: string | null,
  ): void {
    setState((prev) => {
      const loading = new Set(prev.loading);
      loading.delete(key);
      const responses = new Map(prev.responses);
      const errors = new Map(prev.errors);
      if (response !== null) {
        responses.set(key, response);
        errors.delete(key);
      } else {
        errors.set(key, errorDetail ?? "unknown error");
        responses.delete(key);
      }
      return { loading, responses, errors };
    });
  }

  async function pullSource(entry: DataSourceEntry): Promise<void> {
    markLoading(entry.key);
    const body = {
      ticker: entry.scope === "ticker" ? ticker : null,
      lookback_days: entry.settings.lookback_days ?? null,
    };
    const result = await pullOne(entry.key, body, abortControllerRef.current.signal);
    recordResult(entry.key, result.response, result.errorDetail);
  }

  async function pullAllTicker(): Promise<void> {
    if (ticker.length === 0) {
      return;
    }
    await Promise.all(
      providerGroups.map(async (group) => {
        for (const source of group.sources) {
          if (!source.settings.enabled) {
            continue;
          }
          await pullSource(source);
        }
      }),
    );
  }

  async function pullAllMacro(): Promise<void> {
    await Promise.all(
      macroSources
        .filter((s) => s.settings.enabled)
        .map((source) => pullSource(source)),
    );
  }

  function applySettingsUpdate(updated: DataSourceEntry): void {
    setSources((prev) =>
      prev.map((source) => (source.key === updated.key ? updated : source)),
    );
  }

  function clearResults(): void {
    setState({
      responses: new Map(),
      errors: new Map(),
      loading: new Set(),
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3 flex-wrap">
        <label className="flex flex-col text-xs text-fg-muted">
          Ticker
          <Input
            value={ticker}
            onChange={(event) => setTicker(event.target.value.toUpperCase())}
            placeholder="AAPL"
            maxLength={16}
            className="w-[140px]"
            aria-label="ticker"
          />
        </label>
        <Button
          variant="primary"
          size="sm"
          onClick={() => {
            void pullAllTicker();
          }}
          disabled={ticker.length === 0}
        >
          Pull All
        </Button>
        <Button variant="secondary" size="sm" onClick={clearResults}>
          Clear results
        </Button>
        <span className="text-xs text-fg-muted ml-auto">
          {enabledCount} enabled · {disabledCount} disabled
        </span>
      </div>
      <StatusStrip
        enabledSources={enabledTickerSources}
        results={pillStates}
      />
      <div className="flex flex-col gap-4">
        {providerGroups.map((group) => (
          <section
            key={group.provider}
            aria-labelledby={`provider-${group.provider}`}
          >
            <h3
              id={`provider-${group.provider}`}
              className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted pb-2"
            >
              {group.provider}
            </h3>
            <div className="flex flex-col gap-2">
              {group.sources.map((entry) => (
                <SourceRow
                  key={entry.key}
                  entry={entry}
                  ticker={ticker}
                  result={state.responses.get(entry.key) ?? null}
                  errorDetail={state.errors.get(entry.key) ?? null}
                  isLoading={state.loading.has(entry.key)}
                  onPull={(target) => {
                    void pullSource(target);
                  }}
                  onSettingsUpdated={applySettingsUpdate}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
      <MacroSection
        sources={macroSources}
        results={state.responses}
        errors={state.errors}
        loadingKeys={state.loading}
        onPull={(target) => {
          void pullSource(target);
        }}
        onPullAll={() => {
          void pullAllMacro();
        }}
        onSettingsUpdated={applySettingsUpdate}
      />
    </div>
  );
}
