from __future__ import annotations

from collections.abc import Iterable

CURATED_UNIVERSE: tuple[str, ...] = (
    "SPY", "QQQ", "DIA", "IWM", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP",
    "XLI", "XLU", "XLB", "XLRE", "XLC", "VTI", "VOO", "GLD", "TLT", "HYG",
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "BRK.B", "JPM",
    "V", "MA", "UNH", "HD", "PG", "JNJ", "COST", "WMT", "BAC", "KO",
    "PEP", "ADBE", "CRM", "NFLX", "AMD", "INTC", "CSCO", "ORCL", "QCOM", "TXN",
    "DIS", "NKE", "MCD", "ABT", "TMO", "LIN", "ACN", "DHR", "WFC", "GS",
    "MS", "C", "AXP", "CAT", "BA", "GE", "HON", "UPS", "LMT", "RTX",
    "PFE", "MRK", "ABBV", "LLY", "BMY", "CVX", "XOM", "COP", "SLB", "PLTR",
)


def resolve_universe(tickers: Iterable[str] | None = None) -> tuple[str, ...]:
    """Return a deterministic, de-duplicated, upper-cased, sorted ticker tuple.

    Passing `None` resolves the curated liquid large-cap + major-ETF list.
    Passing an explicit iterable overrides it (e.g. an operator watchlist).
    """
    source = CURATED_UNIVERSE if tickers is None else tuple(tickers)
    return tuple(sorted({t.strip().upper() for t in source if t.strip()}))


__all__ = ["CURATED_UNIVERSE", "resolve_universe"]
