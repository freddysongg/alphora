import { describe, expect, test, vi, beforeEach } from "vitest";

const postMock = vi.fn();

vi.mock("@/lib/api", () => ({
  getBrowserApi: (): { POST: typeof postMock } => ({ POST: postMock }),
  isApiError: (): boolean => false,
}));

import { pullOne } from "@/lib/data-health/test-pull-client";
import type {
  TestPullRequest,
  TestPullResponse,
} from "@/lib/data-health/types";

const BODY: TestPullRequest = { ticker: "AAPL", lookback_days: 30 };

const OK_RESPONSE: TestPullResponse = {
  source_key: "finnhub_news",
  status: "ok",
  latency_ms: 12,
  count: 1,
  as_of: null,
  preview: [{ headline: "h" }],
  raw: "[]",
  error: null,
};

describe("pullOne", () => {
  beforeEach(() => {
    postMock.mockReset();
  });

  test("returns the response on success", async () => {
    postMock.mockResolvedValue({ data: OK_RESPONSE });
    const result = await pullOne("finnhub_news", BODY);
    expect(result.sourceKey).toBe("finnhub_news");
    expect(result.response?.status).toBe("ok");
    expect(result.errorDetail).toBeNull();
  });

  test("removes its abort listener from the external signal after completion", async () => {
    postMock.mockResolvedValue({ data: OK_RESPONSE });
    const external = new AbortController();
    const removeSpy = vi.spyOn(external.signal, "removeEventListener");
    await pullOne("finnhub_news", BODY, external.signal);
    expect(removeSpy).toHaveBeenCalledWith("abort", expect.any(Function));
  });
});
