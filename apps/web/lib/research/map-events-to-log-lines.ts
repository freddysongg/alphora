import type { LogLine } from "@/components/ui/log-viewer";
import type { components } from "@/lib/api";
import { formatLogTimestamp } from "@/lib/format/log-timestamp";

type RunEvent = components["schemas"]["RunEventPublic"];

export function mapEventsToLogLines(
  events: readonly RunEvent[],
): LogLine[] {
  const ordered = [...events].sort((left, right) => {
    const leftMs = Date.parse(left.at);
    const rightMs = Date.parse(right.at);
    if (Number.isNaN(leftMs) || Number.isNaN(rightMs)) {
      return 0;
    }
    return leftMs - rightMs;
  });
  return ordered.map((event) => ({
    id: event.id,
    ts: formatLogTimestamp(event.at),
    level: event.level,
    message: event.message,
  }));
}
