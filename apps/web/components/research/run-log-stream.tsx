"use client";

import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";
import { useRouter } from "next/navigation";

import { LogViewer } from "@/components/ui/log-viewer";
import type { LogLevel, LogLine } from "@/components/ui/log-viewer";
import { formatLogTimestamp } from "@/lib/format/log-timestamp";

export interface RunLogStreamProps {
  runId: string;
  initialLines: LogLine[];
  isTerminal: boolean;
}

interface RawLogEvent {
  id?: unknown;
  at?: unknown;
  level?: unknown;
  message?: unknown;
}

const KNOWN_LEVELS: readonly LogLevel[] = ["info", "warn", "err"];
const RECONNECT_DELAYS_MS: readonly number[] = [500, 2000];
const SSE_EVENT_LOG = "log";
const SSE_EVENT_END = "end";

function isKnownLevel(value: string): value is LogLevel {
  return (KNOWN_LEVELS as readonly string[]).includes(value);
}

function toLogLevel(value: unknown): LogLevel {
  if (typeof value === "string" && isKnownLevel(value)) {
    return value;
  }
  return "info";
}

function toLogLine(raw: RawLogEvent, fallbackKey: string): LogLine {
  const at = typeof raw.at === "string" ? raw.at : "";
  const message = typeof raw.message === "string" ? raw.message : "";
  const id = typeof raw.id === "string" ? raw.id : fallbackKey;
  return {
    id,
    ts: formatLogTimestamp(at),
    level: toLogLevel(raw.level),
    message,
  };
}

function parseLogEvent(payload: string, fallbackKey: string): LogLine | null {
  try {
    const parsed: unknown = JSON.parse(payload);
    if (typeof parsed !== "object" || parsed === null) {
      return null;
    }
    return toLogLine(parsed as RawLogEvent, fallbackKey);
  } catch {
    return null;
  }
}

export function RunLogStream(props: RunLogStreamProps): ReactElement {
  const { runId, initialLines, isTerminal } = props;
  const [lines, setLines] = useState<LogLine[]>(initialLines);
  const router = useRouter();

  const appendLine = useCallback((line: LogLine): void => {
    setLines((prev) => [...prev, line]);
  }, []);

  useEffect(() => {
    if (isTerminal) {
      return;
    }

    let isDisposed = false;
    let attempt = 0;
    let activeSource: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const clearReconnectTimer = (): void => {
      if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    const closeActiveSource = (): void => {
      if (activeSource !== null) {
        activeSource.close();
        activeSource = null;
      }
    };

    const handleEnd = (): void => {
      if (isDisposed) {
        return;
      }
      isDisposed = true;
      clearReconnectTimer();
      closeActiveSource();
      router.refresh();
    };

    const open = (): void => {
      if (isDisposed) {
        return;
      }
      const source = new EventSource(`/api/research-runs/${runId}/events`);
      activeSource = source;

      source.addEventListener(SSE_EVENT_LOG, (rawEvent) => {
        const messageEvent = rawEvent as MessageEvent<string>;
        const fallbackKey = `${runId}:${messageEvent.lastEventId || `${Date.now()}-${attempt}`}`;
        const line = parseLogEvent(messageEvent.data, fallbackKey);
        if (line !== null) {
          appendLine(line);
        }
      });

      source.addEventListener(SSE_EVENT_END, handleEnd);

      source.onerror = (): void => {
        if (isDisposed) {
          return;
        }
        closeActiveSource();
        const nextDelay = RECONNECT_DELAYS_MS[attempt];
        attempt += 1;
        if (nextDelay === undefined) {
          isDisposed = true;
          router.refresh();
          return;
        }
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null;
          open();
        }, nextDelay);
      };
    };

    open();

    return (): void => {
      isDisposed = true;
      clearReconnectTimer();
      closeActiveSource();
    };
  }, [runId, isTerminal, appendLine, router]);

  return <LogViewer lines={lines} />;
}
