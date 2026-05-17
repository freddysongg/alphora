import { formatDateTime } from "../date-time";

const _validIso: string = formatDateTime("2026-05-16T14:32:01.124Z");
const _zoned: string = formatDateTime("2026-05-16T14:32:01.124+00:00");
const _empty: string = formatDateTime("");
const _garbage: string = formatDateTime("not-a-date");

const _formattedShape: boolean = _validIso === "2026-05-16 14:32:01";
const _zonedStable: boolean = _zoned === "2026-05-16 14:32:01";
const _fallback: boolean = _empty === "—" && _garbage === "—";

void _validIso;
void _zoned;
void _empty;
void _garbage;
void _formattedShape;
void _zonedStable;
void _fallback;

export {};
