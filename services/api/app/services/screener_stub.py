import random
from typing import Final

from app.schemas.common import ScreenerUniverseEnum

_SP500_SAMPLE: Final[list[str]] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "JPM", "JNJ", "V",
    "WMT", "PG", "MA", "UNH", "HD", "DIS", "BAC", "ADBE", "CRM", "CMCSA",
    "PFE", "KO", "PEP", "INTC", "CSCO", "VZ", "ABT", "T", "MRK", "NFLX",
    "XOM", "CVX", "ORCL", "QCOM", "TXN", "ABBV", "AVGO", "ACN", "COST", "MCD",
    "WFC", "DHR", "MDT", "LIN", "NEE", "BMY", "PM", "HON", "UNP", "LOW",
]

_NASDAQ100_SAMPLE: Final[list[str]] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "ADBE", "NFLX",
    "PEP", "INTC", "CSCO", "CMCSA", "AVGO", "QCOM", "TXN", "AMD", "INTU",
    "AMAT", "BKNG", "MU", "ADP", "GILD", "MDLZ", "ISRG", "ADI", "REGN", "ATVI",
    "VRTX", "LRCX", "FISV", "ASML", "ILMN", "CSX", "BIIB", "EA", "MAR",
    "EXC", "KHC", "WBA", "ROST", "KLAC", "MNST", "PCAR", "SIRI", "PAYX",
    "ORLY", "CTAS", "XEL", "FAST",
]


def get_universe_tickers(universe: ScreenerUniverseEnum) -> list[str]:
    if universe == ScreenerUniverseEnum.sp500:
        return list(_SP500_SAMPLE)
    if universe == ScreenerUniverseEnum.nasdaq100:
        return list(_NASDAQ100_SAMPLE)
    return []


def score_tickers(
    tickers: list[str],
    factor_weights: dict[str, float],
    *,
    seed: int | None = None,
) -> list[tuple[str, float, dict[str, float]]]:
    """Synthesize per-ticker scores using uniform-random factor draws.

    Returns a list of `(ticker, total_score, factor_scores)` tuples sorted by
    score descending. Deterministic when `seed` is provided.
    """
    rng = random.Random(seed)
    scored: list[tuple[str, float, dict[str, float]]] = []
    for ticker in tickers:
        factor_scores: dict[str, float] = {}
        total: float = 0.0
        for factor, weight in factor_weights.items():
            draw = rng.uniform(0.0, 1.0)
            factor_scores[factor] = draw
            total += weight * draw
        scored.append((ticker, total, factor_scores))
    scored.sort(key=lambda entry: entry[1], reverse=True)
    return scored
