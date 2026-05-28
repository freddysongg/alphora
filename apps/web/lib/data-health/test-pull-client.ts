import { getBrowserApi, isApiError } from "@/lib/api";
import type {
  DataSourceEntry,
  TestPullRequest,
  TestPullResponse,
} from "@/lib/data-health/types";

const TIMEOUT_MS = 30_000;

export interface PullResult {
  readonly sourceKey: string;
  readonly response: TestPullResponse | null;
  readonly errorDetail: string | null;
}

export interface ProviderGroup {
  readonly provider: string;
  readonly sources: ReadonlyArray<DataSourceEntry>;
}

export function groupForProviderSerialization(
  sources: ReadonlyArray<DataSourceEntry>,
): ReadonlyArray<ProviderGroup> {
  const order: string[] = [];
  const byProvider: Map<string, DataSourceEntry[]> = new Map();
  for (const source of sources) {
    const existing = byProvider.get(source.provider);
    if (existing === undefined) {
      const list: DataSourceEntry[] = [source];
      byProvider.set(source.provider, list);
      order.push(source.provider);
    } else {
      existing.push(source);
    }
  }
  return order.map((provider) => ({
    provider,
    sources: byProvider.get(provider) ?? [],
  }));
}

function mergeAbortSignals(a: AbortSignal, b: AbortSignal): AbortSignal {
  const controller = new AbortController();
  const forward = (signal: AbortSignal): void => {
    if (signal.aborted) {
      controller.abort(signal.reason);
      return;
    }
    signal.addEventListener(
      "abort",
      () => controller.abort(signal.reason),
      { once: true },
    );
  };
  forward(a);
  forward(b);
  return controller.signal;
}

export async function pullOne(
  sourceKey: string,
  body: TestPullRequest,
  signal?: AbortSignal,
): Promise<PullResult> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const combinedSignal: AbortSignal =
    signal === undefined
      ? controller.signal
      : mergeAbortSignals(signal, controller.signal);
  try {
    const { data } = await getBrowserApi().POST(
      "/api/data-sources/{source_key}/test-pull",
      {
        params: { path: { source_key: sourceKey } },
        body,
        signal: combinedSignal,
      },
    );
    if (data === undefined) {
      return { sourceKey, response: null, errorDetail: "empty response" };
    }
    return { sourceKey, response: data, errorDetail: null };
  } catch (caught) {
    if (isApiError(caught)) {
      return { sourceKey, response: null, errorDetail: caught.detail };
    }
    if (caught instanceof DOMException && caught.name === "AbortError") {
      return { sourceKey, response: null, errorDetail: "timed out" };
    }
    throw caught;
  } finally {
    clearTimeout(timeout);
  }
}

export interface PullAllArgs {
  readonly ticker: string;
  readonly sources: ReadonlyArray<DataSourceEntry>;
  readonly onResult: (result: PullResult) => void;
  readonly signal?: AbortSignal;
}

export async function pullAll(args: PullAllArgs): Promise<void> {
  const enabled = args.sources.filter((s) => s.settings.enabled);
  const groups = groupForProviderSerialization(enabled);
  await Promise.all(
    groups.map(async (group) => {
      for (const source of group.sources) {
        if (args.signal?.aborted === true) {
          return;
        }
        const body: TestPullRequest = {
          ticker: source.scope === "ticker" ? args.ticker : null,
          lookback_days: source.settings.lookback_days ?? null,
        };
        const result = await pullOne(source.key, body, args.signal);
        args.onResult(result);
      }
    }),
  );
}
