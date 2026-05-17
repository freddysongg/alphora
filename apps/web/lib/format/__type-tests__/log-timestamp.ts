import { formatLogTimestamp } from "../log-timestamp";

const _validIso: string = formatLogTimestamp("2026-05-16T14:32:01.124Z");
const _zoned: string = formatLogTimestamp("2026-05-16T14:32:01.124+00:00");
const _empty: string = formatLogTimestamp("");
const _garbage: string = formatLogTimestamp("not-a-date");

const _padded: boolean = _validIso === "14:32:01.124";
const _fallback: boolean = _empty === "--:--:--.---" && _garbage === "--:--:--.---";
const _zonedStable: boolean = _zoned === "14:32:01.124";

void _validIso;
void _zoned;
void _empty;
void _garbage;
void _padded;
void _fallback;
void _zonedStable;

export {};
