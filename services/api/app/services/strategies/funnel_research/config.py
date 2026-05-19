from typing import Final

SYNTHESIS_MODEL: Final[str] = "gpt-5-mini"
MAX_REGENERATIONS: Final[int] = 2
PROMPT_VERSION: Final[str] = "macro-brief-v1"

FRED_SERIES: Final[tuple[str, ...]] = (
    "CPIAUCSL",
    "UNRATE",
    "FEDFUNDS",
    "GS10",
    "GS2",
)

ALLOWED_SECTOR_NAMES: Final[frozenset[str]] = frozenset(
    {
        "Energy",
        "Materials",
        "Industrials",
        "Consumer Discretionary",
        "Consumer Staples",
        "Health Care",
        "Financials",
        "Information Technology",
        "Communication Services",
        "Utilities",
        "Real Estate",
    }
)

TIINGO_NEWS_FETCH_LIMIT: Final[int] = 50
POLYMARKET_FETCH_LIMIT: Final[int] = 100
KALSHI_FETCH_LIMIT: Final[int] = 100
CONGRESS_BILLS_FETCH_LIMIT: Final[int] = 50


__all__ = [
    "ALLOWED_SECTOR_NAMES",
    "CONGRESS_BILLS_FETCH_LIMIT",
    "FRED_SERIES",
    "KALSHI_FETCH_LIMIT",
    "MAX_REGENERATIONS",
    "POLYMARKET_FETCH_LIMIT",
    "PROMPT_VERSION",
    "SYNTHESIS_MODEL",
    "TIINGO_NEWS_FETCH_LIMIT",
]
