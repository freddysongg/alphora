import { dedupeTickers } from "../dedupe-tickers";

const _empty: string[] = dedupeTickers([]);
const _single: string[] = dedupeTickers([{ ticker: "AAPL" }]);
const _deduped: string[] = dedupeTickers([
  { ticker: "MSFT" },
  { ticker: "AAPL" },
  { ticker: "MSFT" },
]);
const _sorted: string[] = dedupeTickers([
  { ticker: "NVDA" },
  { ticker: "AAPL" },
  { ticker: "GOOGL" },
]);

const _emptyShape: boolean = _empty.length === 0;
const _singleShape: boolean = _single.length === 1 && _single[0] === "AAPL";
const _dedupedShape: boolean =
  _deduped.length === 2 && _deduped[0] === "AAPL" && _deduped[1] === "MSFT";
const _sortedShape: boolean =
  _sorted.length === 3 &&
  _sorted[0] === "AAPL" &&
  _sorted[1] === "GOOGL" &&
  _sorted[2] === "NVDA";

void _empty;
void _single;
void _deduped;
void _sorted;
void _emptyShape;
void _singleShape;
void _dedupedShape;
void _sortedShape;

export {};
