import pytest
from pydantic import ValidationError

from app.schemas.data_sources import (
    DataSourceEntryPublic,
    DataSourceSettingsUpdate,
    DataSourceTestPullRequest,
)


def test_settings_update_rejects_invalid_lookback() -> None:
    with pytest.raises(ValidationError):
        DataSourceSettingsUpdate(lookback_days=15)


def test_settings_update_accepts_allowed_lookback() -> None:
    payload = DataSourceSettingsUpdate(lookback_days=30, enabled=False, notes="hi")
    assert payload.lookback_days == 30
    assert payload.enabled is False
    assert payload.notes == "hi"


def test_test_pull_request_uppercases_ticker() -> None:
    payload = DataSourceTestPullRequest(ticker="aapl")
    assert payload.ticker == "AAPL"


def test_test_pull_request_validates_ticker_charset() -> None:
    with pytest.raises(ValidationError):
        DataSourceTestPullRequest(ticker="not a ticker")


def test_entry_public_round_trip() -> None:
    entry = DataSourceEntryPublic.model_validate(
        {
            "key": "finnhub_news",
            "provider": "finnhub",
            "label": "Finnhub Company News",
            "caption": "Recent news headlines for the symbol.",
            "scope": "ticker",
            "default_lookback_days": 30,
            "api_key_env": "FINNHUB_API_KEY",
            "api_key_status": "configured",
            "preview_columns": ["headline", "source", "published_at"],
            "settings": {
                "enabled": True,
                "lookback_days": None,
                "notes": None,
                "updated_at": None,
            },
        }
    )
    assert entry.scope == "ticker"
    assert entry.preview_columns == ("headline", "source", "published_at")
