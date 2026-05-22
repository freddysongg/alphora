"use client";

import { useEffect, useState } from "react";
import type { components } from "@/lib/api";

type RunStatus = components["schemas"]["RunStatusEnum"];

export interface RunStageProgress {
  stageIndex: number | null;
  stageName: string | null;
}

interface StageEventData {
  event: "stage";
  stageName: string;
  stageIndex: number;
}

function isRecord(input: unknown): input is Record<string, unknown> {
  return typeof input === "object" && input !== null && !Array.isArray(input);
}

function parseStageEvent(raw: string): StageEventData | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(parsed)) {
    return null;
  }
  const inner = parsed["data"];
  if (!isRecord(inner)) {
    return null;
  }
  if (inner["event"] !== "stage") {
    return null;
  }
  const stageName = inner["stage_name"];
  const stageIndex = inner["stage_index"];
  if (typeof stageName !== "string" || typeof stageIndex !== "number") {
    return null;
  }
  if (!Number.isInteger(stageIndex) || stageIndex < 1) {
    return null;
  }
  return { event: "stage", stageName, stageIndex };
}

function isTerminalStatus(status: RunStatus): boolean {
  return (
    status === "succeeded" || status === "failed" || status === "cancelled"
  );
}

export function useRunStageProgress(
  runId: string,
  status: RunStatus,
): RunStageProgress {
  const [progress, setProgress] = useState<RunStageProgress>({
    stageIndex: null,
    stageName: null,
  });

  useEffect(() => {
    if (isTerminalStatus(status)) {
      return;
    }
    const source = new EventSource(`/api/research-runs/${runId}/events`);
    function onLog(event: MessageEvent<string>): void {
      const stage = parseStageEvent(event.data);
      if (stage === null) {
        return;
      }
      setProgress((prev) => {
        if (
          prev.stageIndex !== null &&
          prev.stageIndex >= stage.stageIndex &&
          prev.stageName === stage.stageName
        ) {
          return prev;
        }
        return {
          stageIndex: stage.stageIndex,
          stageName: stage.stageName,
        };
      });
    }
    function onError(): void {
      console.warn(`[useRunStageProgress] SSE error for run ${runId}`);
    }
    source.addEventListener("log", onLog as EventListener);
    source.addEventListener("error", onError);
    return (): void => {
      source.removeEventListener("log", onLog as EventListener);
      source.removeEventListener("error", onError);
      source.close();
    };
  }, [runId, status]);

  return progress;
}
