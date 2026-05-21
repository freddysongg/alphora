import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { RunTimelineFlame } from "@/components/research/run-timeline-flame";
import type { components } from "@/lib/api";

type LlmCallLog = components["schemas"]["LlmCallLogPublic"];

const RUN_ID = "11111111-1111-4111-8111-111111111111";

function makeCall(overrides: Partial<LlmCallLog> = {}): LlmCallLog {
  return {
    id: overrides.id ?? crypto.randomUUID(),
    run_id: RUN_ID,
    model: "gpt-5",
    prompt_hash: "x".repeat(64),
    input_hash: "y".repeat(64),
    input_tokens: 1000,
    output_tokens: 200,
    cached_input_tokens: 100,
    reasoning_tokens: 0,
    cost_usd: "0.10",
    latency_ms: 1500,
    status: "success",
    error_message: null,
    evidence_ids: null,
    prompt_version: "v1",
    stage: "macro_synthesis",
    agent_name: "synthesis",
    call_index: 0,
    temperature: 1.0,
    seed: null,
    reasoning_effort: null,
    input_payload: null,
    output_content: null,
    budget_action: "allow",
    created_at: "2026-05-20T10:00:00.000Z",
    ...overrides,
  };
}

describe("RunTimelineFlame", () => {
  it("renders an empty placeholder when there are no calls", () => {
    render(<RunTimelineFlame calls={[]} />);
    expect(
      screen.getByText("No LLM calls recorded for this run yet."),
    ).toBeInTheDocument();
  });

  it("renders one bar per call grouped by stage", () => {
    render(
      <RunTimelineFlame
        calls={[
          makeCall({
            id: "a",
            stage: "macro_synthesis",
            created_at: "2026-05-20T10:00:00.000Z",
          }),
          makeCall({
            id: "b",
            stage: "extraction",
            created_at: "2026-05-20T10:00:02.000Z",
          }),
          makeCall({
            id: "c",
            stage: "macro_synthesis",
            created_at: "2026-05-20T10:00:05.000Z",
          }),
        ]}
      />,
    );
    const bars = screen.getAllByTestId("run-timeline-bar");
    expect(bars).toHaveLength(3);
    expect(screen.getByText(/3 CALLS/)).toBeInTheDocument();
  });

  it("opens the detail panel when a bar is hovered", () => {
    render(
      <RunTimelineFlame
        calls={[
          makeCall({
            id: "a",
            stage: "macro_synthesis",
            agent_name: "synthesis",
            cost_usd: "0.4321",
          }),
        ]}
      />,
    );
    const bar = screen.getByTestId("run-timeline-bar");
    fireEvent.mouseEnter(bar);
    const panel = screen.getByTestId("run-timeline-selected");
    expect(panel).toBeInTheDocument();
    expect(panel.textContent).toContain("$0.4321");
    expect(panel.textContent).toContain("macro_synthesis");
  });

  it("renders stage rows for every distinct stage in the data", () => {
    render(
      <RunTimelineFlame
        calls={[
          makeCall({ id: "a", stage: "macro_synthesis" }),
          makeCall({ id: "b", stage: "judge" }),
          makeCall({ id: "c", stage: "extraction" }),
        ]}
      />,
    );
    expect(screen.getByText("macro_synthesis")).toBeInTheDocument();
    expect(screen.getByText("judge")).toBeInTheDocument();
    expect(screen.getByText("extraction")).toBeInTheDocument();
  });

  it("treats created_at as the call's *end* time and shifts bars back by latency", () => {
    // Two parallel calls that started at the same time (t=0):
    //   A: 10s long → created_at = +10s
    //   B: 30s long → created_at = +30s
    // Total elapsed must be 30s, not 30s + 30s = 60s.
    render(
      <RunTimelineFlame
        calls={[
          makeCall({
            id: "a",
            stage: "macro_synthesis",
            latency_ms: 10_000,
            created_at: "2026-05-20T10:00:10.000Z",
          }),
          makeCall({
            id: "b",
            stage: "extraction",
            latency_ms: 30_000,
            created_at: "2026-05-20T10:00:30.000Z",
          }),
        ]}
      />,
    );
    expect(screen.getByText(/30\.0s TOTAL/)).toBeInTheDocument();
    const bars = screen.getAllByTestId("run-timeline-bar");
    expect(bars).toHaveLength(2);
    // Both calls should start at left:0% (they began at the same wall time).
    bars.forEach((bar) => {
      expect((bar as HTMLElement).style.left).toBe("0%");
    });
  });
});
