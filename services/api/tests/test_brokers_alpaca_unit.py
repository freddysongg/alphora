from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.brokers.alpaca import AlpacaAdapter


def test_adapter_stores_mode_and_clients() -> None:
    trading = MagicMock()
    data = MagicMock()
    adapter = AlpacaAdapter(trading_client=trading, data_client=data, mode="paper")
    assert adapter.mode == "paper"
    assert adapter._trading is trading
    assert adapter._data is data


def test_from_env_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="ALPACA_API_KEY"):
        AlpacaAdapter.from_env()


def test_from_env_constructs_paper_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "PK_TEST")
    monkeypatch.setenv("ALPACA_API_SECRET", "SK_TEST")
    monkeypatch.setenv("ALPACA_MODE", "paper")
    from app.config import get_settings

    get_settings.cache_clear()
    adapter = AlpacaAdapter.from_env()
    assert adapter.mode == "paper"


def test_from_env_constructs_live_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "AK_TEST")
    monkeypatch.setenv("ALPACA_API_SECRET", "AS_TEST")
    monkeypatch.setenv("ALPACA_MODE", "live")
    from app.config import get_settings

    get_settings.cache_clear()
    adapter = AlpacaAdapter.from_env()
    assert adapter.mode == "live"


@pytest.mark.asyncio
async def test_get_account_translates_alpaca_response() -> None:
    fake_response = SimpleNamespace(
        id="acct-1",
        cash="123.45",
        equity="200.00",
        buying_power="500.00",
        pattern_day_trader=False,
    )
    trading = MagicMock()
    trading.get_account = MagicMock(return_value=fake_response)
    adapter = AlpacaAdapter(trading_client=trading, data_client=MagicMock(), mode="paper")

    account = await adapter.get_account()

    assert account.account_id == "acct-1"
    assert account.cash == Decimal("123.45")
    assert account.equity == Decimal("200.00")
    assert account.buying_power == Decimal("500.00")
    assert account.pattern_day_trader is False
