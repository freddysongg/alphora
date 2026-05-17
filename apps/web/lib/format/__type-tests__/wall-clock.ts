import { formatWallClock } from "../wall-clock";

const _nullValue: string = formatWallClock(null);
const _undefinedValue: string = formatWallClock(undefined);
const _seconds: string = formatWallClock(5_000);
const _minutes: string = formatWallClock(204_000);
const _hours: string = formatWallClock(3_720_000);
const _negative: string = formatWallClock(-1);

const _nullIsDash: boolean = _nullValue === "—";
const _undefinedIsDash: boolean = _undefinedValue === "—";
const _secondsShape: boolean = _seconds === "5s";
const _minutesShape: boolean = _minutes === "3m 24s";
const _hoursShape: boolean = _hours === "1h 02m";
const _negativeIsDash: boolean = _negative === "—";

void _nullValue;
void _undefinedValue;
void _seconds;
void _minutes;
void _hours;
void _negative;
void _nullIsDash;
void _undefinedIsDash;
void _secondsShape;
void _minutesShape;
void _hoursShape;
void _negativeIsDash;

export {};
