import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { HumanReviewForm } from "@/components/research/human-review-form";

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

describe("HumanReviewForm", () => {
  beforeEach(() => {
    postMock.mockReset();
  });

  it("renders both axis fieldsets and reviewer + week start inputs", () => {
    render(<HumanReviewForm defaultWeekStart="2026-05-18" />);
    expect(
      screen.getByRole("group", {
        name: /surfaced something i'd have missed/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: /missed something i noticed/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/reviewer/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/week start/i)).toHaveValue("2026-05-18");
  });

  it("submits the form to the human-reviews endpoint with the selected axis values", async () => {
    postMock.mockResolvedValue({
      data: {
        id: "00000000-0000-4000-8000-000000000010",
        run_id: null,
        brief_kind: null,
        week_start: "2026-05-18",
        reviewer: "alice",
        surfaced_missed: 2,
        missed_noticed: -1,
        notes: null,
        created_at: "2026-05-19T12:00:00Z",
      },
    });
    render(<HumanReviewForm defaultWeekStart="2026-05-18" />);
    fireEvent.change(screen.getByLabelText(/reviewer/i), {
      target: { value: "alice" },
    });
    const surfacedGroup = screen.getByRole("group", {
      name: /surfaced something i'd have missed/i,
    });
    const surfacedOptions = surfacedGroup.querySelectorAll(
      "input[name='surfaced_missed']",
    );
    const surfacedPlusTwo = surfacedOptions[4];
    if (!(surfacedPlusTwo instanceof HTMLInputElement)) {
      throw new Error("missing surfaced +2 option");
    }
    fireEvent.click(surfacedPlusTwo);
    const missedGroup = screen.getByRole("group", {
      name: /missed something i noticed/i,
    });
    const missedOptions = missedGroup.querySelectorAll(
      "input[name='missed_noticed']",
    );
    const missedMinusOne = missedOptions[1];
    if (!(missedMinusOne instanceof HTMLInputElement)) {
      throw new Error("missing missed -1 option");
    }
    fireEvent.click(missedMinusOne);
    fireEvent.submit(screen.getByRole("form", { name: /human review/i }));
    await waitFor(() => {
      expect(postMock).toHaveBeenCalledOnce();
    });
    const firstCall = postMock.mock.calls[0];
    if (firstCall === undefined) {
      throw new Error("expected one POST call");
    }
    const path = firstCall[0];
    const args = firstCall[1];
    expect(path).toBe("/api/human-reviews");
    expect(args.body.reviewer).toBe("alice");
    expect(args.body.surfaced_missed).toBe(2);
    expect(args.body.missed_noticed).toBe(-1);
  });

  it("invokes onSubmitted exactly once after a successful save so the parent can refresh the summary", async () => {
    postMock.mockResolvedValue({
      data: {
        id: "00000000-0000-4000-8000-000000000011",
        run_id: null,
        brief_kind: null,
        week_start: "2026-05-18",
        reviewer: "alice",
        surfaced_missed: 0,
        missed_noticed: 0,
        notes: null,
        created_at: "2026-05-19T12:00:00Z",
      },
    });
    const onSubmitted = vi.fn();
    render(
      <HumanReviewForm
        defaultWeekStart="2026-05-18"
        onSubmitted={onSubmitted}
      />,
    );
    fireEvent.change(screen.getByLabelText(/reviewer/i), {
      target: { value: "alice" },
    });
    fireEvent.submit(screen.getByRole("form", { name: /human review/i }));
    await waitFor(() => {
      expect(onSubmitted).toHaveBeenCalledOnce();
    });
  });

  it("does not invoke onSubmitted when the API rejects the save", async () => {
    postMock.mockRejectedValue({
      status: 422,
      detail: "axis out of range",
    });
    const onSubmitted = vi.fn();
    render(
      <HumanReviewForm
        defaultWeekStart="2026-05-18"
        onSubmitted={onSubmitted}
      />,
    );
    fireEvent.change(screen.getByLabelText(/reviewer/i), {
      target: { value: "alice" },
    });
    fireEvent.submit(screen.getByRole("form", { name: /human review/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(onSubmitted).not.toHaveBeenCalled();
  });

  it("shows an error message when the API returns an ApiError", async () => {
    postMock.mockRejectedValue({
      status: 422,
      detail: "axis out of range",
    });
    render(<HumanReviewForm defaultWeekStart="2026-05-18" />);
    fireEvent.change(screen.getByLabelText(/reviewer/i), {
      target: { value: "alice" },
    });
    fireEvent.submit(screen.getByRole("form", { name: /human review/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/axis out of range/i);
    });
  });
});
