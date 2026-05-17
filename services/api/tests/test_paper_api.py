import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from app.db.models_paper import PaperPortfolio, PaperPosition
from app.db.session import session_factory
from app.main import app


def _seed_portfolio_with_position(*, ticker: str, quantity: int) -> uuid.UUID:
    async def _do() -> uuid.UUID:
        portfolio = PaperPortfolio(
            id=uuid.uuid4(), name="Test", cash_cents=100_000_00
        )
        position = PaperPosition(
            id=uuid.uuid4(),
            portfolio_id=portfolio.id,
            ticker=ticker,
            quantity=quantity,
            avg_cost_cents=15_000,
            opened_at=datetime.now(UTC),
        )
        async with session_factory() as session:
            session.add(portfolio)
            session.add(position)
            await session.commit()
        return portfolio.id

    return asyncio.run(_do())


def _seed_portfolio() -> uuid.UUID:
    async def _do() -> uuid.UUID:
        portfolio = PaperPortfolio(
            id=uuid.uuid4(), name="Test", cash_cents=100_000_00
        )
        async with session_factory() as session:
            session.add(portfolio)
            await session.commit()
        return portfolio.id

    return asyncio.run(_do())


def test_create_buy_order_succeeds(initialized_schema: None) -> None:
    _ = initialized_schema
    portfolio_id = _seed_portfolio()
    payload: dict[str, Any] = {
        "portfolio_id": str(portfolio_id),
        "ticker": "aapl",
        "side": "buy",
        "quantity": 10,
        "order_type": "market",
    }
    with TestClient(app) as client:
        response = client.post("/api/paper/orders", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["ticker"] == "AAPL"
    assert body["side"] == "buy"


def test_sell_without_open_position_returns_409(initialized_schema: None) -> None:
    _ = initialized_schema
    portfolio_id = _seed_portfolio()
    payload: dict[str, Any] = {
        "portfolio_id": str(portfolio_id),
        "ticker": "AAPL",
        "side": "sell",
        "quantity": 5,
        "order_type": "market",
    }
    with TestClient(app) as client:
        response = client.post("/api/paper/orders", json=payload)
    assert response.status_code == 409


def test_sell_with_open_position_succeeds(initialized_schema: None) -> None:
    _ = initialized_schema
    portfolio_id = _seed_portfolio_with_position(ticker="AAPL", quantity=10)
    payload: dict[str, Any] = {
        "portfolio_id": str(portfolio_id),
        "ticker": "AAPL",
        "side": "sell",
        "quantity": 5,
        "order_type": "market",
    }
    with TestClient(app) as client:
        response = client.post("/api/paper/orders", json=payload)
    assert response.status_code == 201
    assert response.json()["status"] == "pending"


def test_create_order_returns_404_for_unknown_portfolio(initialized_schema: None) -> None:
    _ = initialized_schema
    payload: dict[str, Any] = {
        "portfolio_id": str(uuid.uuid4()),
        "ticker": "AAPL",
        "side": "buy",
        "quantity": 10,
        "order_type": "market",
    }
    with TestClient(app) as client:
        response = client.post("/api/paper/orders", json=payload)
    assert response.status_code == 404


def test_get_portfolio_creates_default_when_none(initialized_schema: None) -> None:
    _ = initialized_schema
    with TestClient(app) as client:
        response = client.get("/api/paper/portfolio")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Default"
    assert body["cash_cents"] == 10_000_000
    assert body["positions"] == []
    assert body["equity_cents"] == 0
    assert body["realized_pl_cents"] == 0


def test_list_orders_filters_by_status(initialized_schema: None) -> None:
    _ = initialized_schema
    portfolio_id = _seed_portfolio()
    payload: dict[str, Any] = {
        "portfolio_id": str(portfolio_id),
        "ticker": "AAPL",
        "side": "buy",
        "quantity": 10,
        "order_type": "market",
    }
    with TestClient(app) as client:
        client.post("/api/paper/orders", json=payload)
        all_orders = client.get(
            "/api/paper/orders", params={"portfolio_id": str(portfolio_id)}
        )
        filled_only = client.get(
            "/api/paper/orders",
            params={"portfolio_id": str(portfolio_id), "status": "filled"},
        )
    assert all_orders.status_code == 200
    assert len(all_orders.json()) == 1
    assert filled_only.status_code == 200
    assert filled_only.json() == []
