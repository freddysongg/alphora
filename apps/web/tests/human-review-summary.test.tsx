import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { HumanReviewSummaryWidget } from "@/components/research/human-review-summary";

describe("HumanReviewSummaryWidget", () => {
  it("renders an empty placeholder when there are no weeks", () => {
    render(<HumanReviewSummaryWidget summary={{ weeks: [] }} />);
    expect(screen.getByText(/no weekly reviews yet/i)).toBeInTheDocument();
  });

  it("renders one row per week with reviewer counts and mean axes", () => {
    render(
      <HumanReviewSummaryWidget
        summary={{
          weeks: [
            {
              week_start: "2026-05-18",
              review_count: 3,
              mean_surfaced_missed: 1.5,
              mean_missed_noticed: -0.5,
            },
            {
              week_start: "2026-05-11",
              review_count: 1,
              mean_surfaced_missed: -1.0,
              mean_missed_noticed: 2.0,
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("2026-05-18")).toBeInTheDocument();
    expect(screen.getByText("2026-05-11")).toBeInTheDocument();
    expect(screen.getByText("1.50")).toBeInTheDocument();
    expect(screen.getByText("-0.50")).toBeInTheDocument();
    expect(screen.getByText("-1.00")).toBeInTheDocument();
    expect(screen.getByText("2.00")).toBeInTheDocument();
  });
});
