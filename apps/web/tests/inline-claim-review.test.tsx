import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import {
  InlineClaimReview,
  type InlineClaim,
} from "@/components/research/inline-claim-review";

const postMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("@/lib/api");
  return {
    ...actual,
    getBrowserApi: () => ({
      POST: postMock,
    }),
    isApiError: (error: unknown): boolean =>
      typeof error === "object"
      && error !== null
      && "status" in error
      && "detail" in error,
  };
});

const RUN_ID = "11111111-1111-4111-8111-111111111111";

function makeClaim(overrides: Partial<InlineClaim> = {}): InlineClaim {
  return {
    chunkId: overrides.chunkId ?? "22222222-2222-4222-8222-222222222222",
    quote: overrides.quote ?? "Quote text",
    briefKind: overrides.briefKind ?? "macro",
    briefId: overrides.briefId ?? "33333333-3333-4333-8333-333333333333",
    source: overrides.source ?? "edgar",
  };
}

describe("InlineClaimReview", () => {
  beforeEach(() => {
    postMock.mockReset();
  });

  it("renders an empty placeholder when no claims", () => {
    render(
      <InlineClaimReview
        runId={RUN_ID}
        defaultWeekStart="2026-05-18"
        reviewer="alice"
        claims={[]}
      />,
    );
    expect(
      screen.getByText("No cited claims to review for this run."),
    ).toBeInTheDocument();
  });

  it("renders one row per cited claim", () => {
    render(
      <InlineClaimReview
        runId={RUN_ID}
        defaultWeekStart="2026-05-18"
        reviewer="alice"
        claims={[
          makeClaim({
            chunkId: "44444444-4444-4444-8444-444444444444",
            quote: "Q1",
          }),
          makeClaim({
            chunkId: "55555555-5555-4555-8555-555555555555",
            quote: "Q2",
            source: "tiingo",
          }),
        ]}
      />,
    );
    const rows = screen.getAllByTestId("inline-claim-review-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]?.textContent).toContain("Q1");
    expect(rows[0]?.textContent).toContain("SOURCE edgar");
    expect(rows[1]?.textContent).toContain("SOURCE tiingo");
  });

  it("posts a human-review with the per-row axis values and chunk_id notes", async () => {
    postMock.mockResolvedValue({
      data: {
        id: "00000000-0000-4000-8000-000000000010",
        run_id: RUN_ID,
        brief_kind: "macro",
        week_start: "2026-05-18",
        reviewer: "alice",
        surfaced_missed: 1,
        missed_noticed: 0,
        notes:
          "chunk_id=44444444-4444-4444-8444-444444444444 brief_id=33333333-3333-4333-8333-333333333333",
        created_at: "2026-05-19T12:00:00Z",
      },
    });
    const claim = makeClaim({
      chunkId: "44444444-4444-4444-8444-444444444444",
      briefId: "33333333-3333-4333-8333-333333333333",
    });
    render(
      <InlineClaimReview
        runId={RUN_ID}
        defaultWeekStart="2026-05-18"
        reviewer="alice"
        claims={[claim]}
      />,
    );
    const surfacedGroup = screen.getByTestId(
      `surfaced-${claim.chunkId}`,
    );
    const plusOne = surfacedGroup.querySelector(
      "button[data-axis-level='1']",
    );
    if (!(plusOne instanceof HTMLButtonElement)) {
      throw new Error("missing +1 surfaced button");
    }
    fireEvent.click(plusOne);
    const saveButton = screen.getByTestId(
      `inline-claim-review-save-${claim.chunkId}`,
    );
    fireEvent.click(saveButton);
    await waitFor(() => {
      expect(postMock).toHaveBeenCalledTimes(1);
    });
    const firstCall = postMock.mock.calls[0];
    if (firstCall === undefined) {
      throw new Error("expected POST mock to be called once");
    }
    const [, options] = firstCall;
    expect(options.body.surfaced_missed).toBe(1);
    expect(options.body.missed_noticed).toBe(0);
    expect(options.body.brief_kind).toBe("macro");
    expect(options.body.run_id).toBe(RUN_ID);
    expect(options.body.notes).toContain(
      "chunk_id=44444444-4444-4444-8444-444444444444",
    );
    expect(options.body.notes).toContain(
      "brief_id=33333333-3333-4333-8333-333333333333",
    );
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });

  it("rejects save when reviewer is empty", async () => {
    const claim = makeClaim();
    render(
      <InlineClaimReview
        runId={RUN_ID}
        defaultWeekStart="2026-05-18"
        reviewer="   "
        claims={[claim]}
      />,
    );
    const saveButton = screen.getByTestId(
      `inline-claim-review-save-${claim.chunkId}`,
    );
    fireEvent.click(saveButton);
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain(
        "Reviewer name is required.",
      );
    });
    expect(postMock).not.toHaveBeenCalled();
  });
});
