from app.services.strategies.funnel_research.sector_constituents import (
    SectorConstituents,
    load_sector_constituents,
)

_TOP_LEVEL_SECTORS: frozenset[str] = frozenset(
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


def test_load_sector_constituents_covers_all_top_level_sectors() -> None:
    constituents = load_sector_constituents()
    assert set(constituents.keys()) == _TOP_LEVEL_SECTORS


def test_constituent_entries_are_bounded() -> None:
    constituents = load_sector_constituents()
    for sector, entry in constituents.items():
        assert isinstance(entry, SectorConstituents), sector
        assert entry.proxy_ticker, sector
        assert 1 <= len(entry.representative_tickers) <= 5, sector


def test_proxy_tickers_are_unique_per_sector() -> None:
    constituents = load_sector_constituents()
    proxies = [entry.proxy_ticker for entry in constituents.values()]
    assert len(proxies) == len(set(proxies))


def test_information_technology_proxy_is_xlk() -> None:
    constituents = load_sector_constituents()
    assert constituents["Information Technology"].proxy_ticker == "XLK"
    assert "AAPL" in constituents["Information Technology"].representative_tickers
