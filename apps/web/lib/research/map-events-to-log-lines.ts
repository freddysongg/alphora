import type { LogLine } from "@/components/ui/log-viewer";
import type { components } from "@/lib/api";
import { formatLogTimestamp } from "@/lib/format/log-timestamp";

type RunEvent = components["schemas"]["RunEventPublic"];

const LOG_PREFIX = "[mapEventsToLogLines]";

const warnedEventIds = new Set<string>();

function parseTimestamp(event: RunEvent): number {
  const parsed = Date.parse(event.at);
  if (Number.isNaN(parsed)) {
    if (!warnedEventIds.has(event.id)) {
      warnedEventIds.add(event.id);
      console.warn(
        `${LOG_PREFIX} unparseable timestamp for event ${event.id}: ${event.at}`,
      );
    }
    return Number.POSITIVE_INFINITY;
  }
  return parsed;
}

export function mapEventsToLogLines(
  events: readonly RunEvent[],
): LogLine[] {
  const ordered = [...events].sort((left, right) => {
    const leftMs = parseTimestamp(left);
    const rightMs = parseTimestamp(right);
    if (leftMs !== rightMs) {
      return leftMs - rightMs;
    }
    return left.id.localeCompare(right.id);
  });
  return ordered.map((event) => ({
    id: event.id,
    ts: formatLogTimestamp(event.at),
    level: event.level,
    message: event.message,
  }));
}
