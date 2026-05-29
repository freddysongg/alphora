from app.schemas.data_sources import ALLOWED_LOOKBACK_DAYS
from app.services.data_sources.registry import (
    DATA_SOURCE_REGISTRY,
    get_entry,
    iter_entries,
)


def test_registry_keys_are_unique() -> None:
    keys = [entry.key for entry in DATA_SOURCE_REGISTRY]
    assert len(keys) == len(set(keys))


def test_registry_covers_all_expected_keys() -> None:
    expected = {
        "finnhub_insider_transactions",
        "finnhub_news",
        "finnhub_peers",
        "finnhub_price_target",
        "finnhub_profile",
        "finnhub_recommendation",
        "polygon_aggregates",
        "sec_filings",
        "tiingo_news_items",
        "gdelt",
        "fred_observations",
        "fed_press",
        "cme_fedwatch",
        "kalshi_markets",
        "polymarket_events",
        "polymarket_price_history",
        "congress_bills",
    }
    actual = {entry.key for entry in DATA_SOURCE_REGISTRY}
    assert actual == expected


def test_registry_lookback_defaults_are_valid() -> None:
    for entry in DATA_SOURCE_REGISTRY:
        if entry.default_lookback_days is None:
            continue
        assert entry.default_lookback_days in ALLOWED_LOOKBACK_DAYS


def test_registry_api_key_env_matches_settings_field() -> None:
    from app.config import Settings

    fields = set(Settings.model_fields.keys())
    for entry in DATA_SOURCE_REGISTRY:
        if entry.api_key_env is None:
            continue
        assert entry.api_key_env in fields, (
            f"{entry.key}: api_key_env={entry.api_key_env!r} not in Settings"
        )


def test_get_entry_known_key() -> None:
    entry = get_entry("finnhub_news")
    assert entry is not None
    assert entry.provider == "finnhub"


def test_get_entry_unknown_key_returns_none() -> None:
    assert get_entry("not_a_source") is None


def test_iter_entries_returns_registry_order() -> None:
    listed = list(iter_entries())
    assert [e.key for e in listed] == [e.key for e in DATA_SOURCE_REGISTRY]
