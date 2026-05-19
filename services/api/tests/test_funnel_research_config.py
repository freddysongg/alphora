def test_constants_are_pinned() -> None:
    from app.services.strategies.funnel_research import config

    assert config.SYNTHESIS_MODEL == "gpt-5-mini"
    assert config.MAX_REGENERATIONS == 2
    assert config.PROMPT_VERSION == "macro-brief-v1"
    assert config.FRED_SERIES == (
        "CPIAUCSL",
        "UNRATE",
        "FEDFUNDS",
        "GS10",
        "GS2",
    )
    assert config.ALLOWED_SECTOR_NAMES == frozenset(
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
    assert config.TIINGO_NEWS_FETCH_LIMIT == 50
    assert config.POLYMARKET_FETCH_LIMIT == 100
    assert config.KALSHI_FETCH_LIMIT == 100
    assert config.CONGRESS_BILLS_FETCH_LIMIT == 50
