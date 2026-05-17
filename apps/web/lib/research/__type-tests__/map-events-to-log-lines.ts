import type { LogLine } from "@/components/ui/log-viewer";
import type { components } from "@/lib/api";
import { mapEventsToLogLines } from "../map-events-to-log-lines";

type RunEvent = components["schemas"]["RunEventPublic"];

const events: readonly RunEvent[] = [
  {
    id: "00000000-0000-0000-0000-000000000002",
    run_id: "00000000-0000-0000-0000-000000000001",
    at: "2026-05-16T14:32:02.012Z",
    level: "info",
    message: "second",
    data: null,
  },
  {
    id: "00000000-0000-0000-0000-000000000003",
    run_id: "00000000-0000-0000-0000-000000000001",
    at: "2026-05-16T14:32:01.124Z",
    level: "warn",
    message: "first",
    data: { key: "value" },
  },
];

const _mapped: LogLine[] = mapEventsToLogLines(events);
const _firstLine: LogLine | undefined = _mapped[0];
const _firstIsEarliest: boolean = _firstLine?.message === "first";
const _levelPreserved: boolean = _firstLine?.level === "warn";
const _timestampShape: boolean = _firstLine?.ts === "14:32:01.124";

void _mapped;
void _firstIsEarliest;
void _levelPreserved;
void _timestampShape;

export {};
