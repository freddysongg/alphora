import { getBrowserApi, isApiError } from "@/lib/api";
import type {
  TestPullRequest,
  TestPullResponse,
} from "@/lib/data-health/types";

const TIMEOUT_MS = 30_000;

export interface PullResult {
  readonly sourceKey: string;
  readonly response: TestPullResponse | null;
  readonly errorDetail: string | null;
}

export async function pullOne(
  sourceKey: string,
  body: TestPullRequest,
  signal?: AbortSignal,
): Promise<PullResult> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const forwardAbort = (): void => controller.abort(signal?.reason);
  if (signal !== undefined) {
    if (signal.aborted) {
      controller.abort(signal.reason);
    } else {
      signal.addEventListener("abort", forwardAbort, { once: true });
    }
  }
  try {
    const { data } = await getBrowserApi().POST(
      "/api/data-sources/{source_key}/test-pull",
      {
        params: { path: { source_key: sourceKey } },
        body,
        signal: controller.signal,
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
    if (signal !== undefined) {
      signal.removeEventListener("abort", forwardAbort);
    }
  }
}
