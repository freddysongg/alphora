from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.brokers.alpaca import AlpacaAdapter
from app.brokers.base import OrderRequest


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


@pytest.mark.asyncio
async def test_get_quote_translates_alpaca_latest_quote() -> None:
    ts = datetime(2026, 5, 20, 14, 30, tzinfo=UTC)
    fake_quote = SimpleNamespace(
        bid_price="500.10",
        ask_price="500.12",
        timestamp=ts,
    )
    fake_trade = SimpleNamespace(price="500.11", timestamp=ts)
    data = MagicMock()
    data.get_stock_latest_quote = MagicMock(return_value={"SPY": fake_quote})
    data.get_stock_latest_trade = MagicMock(return_value={"SPY": fake_trade})
    adapter = AlpacaAdapter(trading_client=MagicMock(), data_client=data, mode="paper")

    quote = await adapter.get_quote("SPY")

    assert quote.ticker == "SPY"
    assert quote.bid == Decimal("500.10")
    assert quote.ask == Decimal("500.12")
    assert quote.last == Decimal("500.11")
    assert quote.as_of == ts


@pytest.mark.asyncio
async def test_get_positions_translates_alpaca_positions() -> None:
    fake_positions = [
        SimpleNamespace(symbol="SPY", qty="2", avg_entry_price="500.00"),
        SimpleNamespace(symbol="QQQ", qty="-1", avg_entry_price="400.00"),
    ]
    trading = MagicMock()
    trading.get_all_positions = MagicMock(return_value=fake_positions)
    adapter = AlpacaAdapter(trading_client=trading, data_client=MagicMock(), mode="paper")

    positions = await adapter.get_positions()

    assert len(positions) == 2
    assert positions[0].ticker == "SPY"
    assert positions[0].quantity == Decimal("2")
    assert positions[0].side == "long"
    assert positions[1].side == "short"


@pytest.mark.asyncio
async def test_get_positions_empty_when_no_positions() -> None:
    trading = MagicMock()
    trading.get_all_positions = MagicMock(return_value=[])
    adapter = AlpacaAdapter(trading_client=trading, data_client=MagicMock(), mode="paper")

    positions = await adapter.get_positions()
    assert positions == []


@pytest.mark.asyncio
async def test_is_tradable_returns_full_tradability_view() -> None:
    fake_asset = SimpleNamespace(
        symbol="SPY",
        tradable=True,
        shortable=True,
        fractionable=True,
        status="active",
    )
    trading = MagicMock()
    trading.get_asset = MagicMock(return_value=fake_asset)
    adapter = AlpacaAdapter(trading_client=trading, data_client=MagicMock(), mode="paper")

    check = await adapter.is_tradable("SPY")
    assert check.ticker == "SPY"
    assert check.is_tradable is True
    assert check.is_shortable is True
    assert check.fractionable is True
    assert check.is_halted is False
    assert check.reason is None


@pytest.mark.asyncio
async def test_is_tradable_flags_inactive_asset_with_reason() -> None:
    fake_asset = SimpleNamespace(
        symbol="XYZ",
        tradable=False,
        shortable=False,
        fractionable=False,
        status="inactive",
    )
    trading = MagicMock()
    trading.get_asset = MagicMock(return_value=fake_asset)
    adapter = AlpacaAdapter(trading_client=trading, data_client=MagicMock(), mode="paper")

    check = await adapter.is_tradable("XYZ")
    assert check.is_tradable is False
    assert check.reason == "asset status: inactive"


@pytest.mark.asyncio
async def test_place_order_market_buy_returns_broker_order_id() -> None:
    submitted = datetime(2026, 5, 20, 14, 30, tzinfo=UTC)
    fake_response = SimpleNamespace(
        id="ord-1",
        client_order_id="cli-1",
        status="new",
        submitted_at=submitted,
    )
    trading = MagicMock()
    trading.submit_order = MagicMock(return_value=fake_response)
    adapter = AlpacaAdapter(trading_client=trading, data_client=MagicMock(), mode="paper")

    req = OrderRequest(
        ticker="SPY",
        side="buy",
        quantity=Decimal("1"),
        order_type="market",
        time_in_force="day",
    )
    resp = await adapter.place_order(req)

    assert resp.broker_order_id == "ord-1"
    assert resp.client_order_id == "cli-1"
    assert resp.status == "new"
    assert trading.submit_order.called


@pytest.mark.asyncio
async def test_place_order_limit_buy_includes_limit_price() -> None:
    fake_response = SimpleNamespace(
        id="ord-2",
        client_order_id=None,
        status="new",
        submitted_at=datetime(2026, 5, 20, 14, 30, tzinfo=UTC),
    )
    trading = MagicMock()
    trading.submit_order = MagicMock(return_value=fake_response)
    adapter = AlpacaAdapter(trading_client=trading, data_client=MagicMock(), mode="paper")

    req = OrderRequest(
        ticker="SPY",
        side="buy",
        quantity=Decimal("1"),
        order_type="limit",
        time_in_force="day",
        limit_price=Decimal("500.00"),
    )
    resp = await adapter.place_order(req)
    assert resp.broker_order_id == "ord-2"
    submitted_arg = trading.submit_order.call_args.args[0]
    assert submitted_arg.limit_price == 500.0
