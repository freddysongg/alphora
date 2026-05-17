import { centsToDollars } from "../cents";

const _nullValue: string = centsToDollars(null);
const _zero: string = centsToDollars(0);
const _small: string = centsToDollars(123456);
const _large: string = centsToDollars(100_000_000);
const _negative: string = centsToDollars(-12345);

const _nullIsDash: boolean = _nullValue === "—";
const _zeroShape: boolean = _zero === "0.00";
const _smallShape: boolean = _small === "1,234.56";
const _largeShape: boolean = _large === "1,000,000.00";
const _negativeShape: boolean = _negative === "-123.45";

void _nullValue;
void _zero;
void _small;
void _large;
void _negative;
void _nullIsDash;
void _zeroShape;
void _smallShape;
void _largeShape;
void _negativeShape;

export {};
