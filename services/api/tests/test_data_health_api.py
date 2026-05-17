import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.db.models_data_health import ProviderCheck, ProviderCheckStatus
from app.db.session import session_factory
from app.main import app


def test_data_health_matrix_empty_when_no_checks(initialized_schema: None) -> None:
    _ = initialized_schema
    with TestClient(app) as client:
        response = client.get("/api/data-health")
    assert response.status_code == 200
    body = response.json()
    assert body == {"providers": [], "tools": [], "cells": []}


def test_data_health_matrix_returns_latest_per_pair(initialized_schema: None) -> None:
    _ = initialized_schema
    now = datetime.now(UTC)

    async def _seed() -> None:
        rows = [
            ProviderCheck(
                id=uuid.uuid4(),
                provider="yfinance",
                tool="price",
                at=now - timedelta(hours=2),
                latency_ms=80,
                status=ProviderCheckStatus.success,
                sample_count=200,
            ),
            ProviderCheck(
                id=uuid.uuid4(),
                provider="yfinance",
                tool="price",
                at=now,
                latency_ms=42,
                status=ProviderCheckStatus.success,
                sample_count=250,
            ),
            ProviderCheck(
                id=uuid.uuid4(),
                provider="alpha_vantage",
                tool="indicators",
                at=now - timedelta(minutes=5),
                latency_ms=120,
                status=ProviderCheckStatus.failure,
                sample_count=0,
            ),
        ]
        async with session_factory() as session:
            for row in rows:
                session.add(row)
            await session.commit()

    asyncio.run(_seed())
    with TestClient(app) as client:
        response = client.get("/api/data-health")
    assert response.status_code == 200
    body = response.json()
    assert body["providers"] == ["alpha_vantage", "yfinance"]
    assert body["tools"] == ["indicators", "price"]
    assert len(body["cells"]) == 2
    yfinance_cell = next(c for c in body["cells"] if c["provider"] == "yfinance")
    assert yfinance_cell["latency_ms"] == 42
    assert yfinance_cell["sample_count"] == 250


def test_data_health_calls_filters_by_provider_and_tool(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    now = datetime.now(UTC)

    async def _seed() -> None:
        rows = [
            ProviderCheck(
                id=uuid.uuid4(),
                provider="yfinance",
                tool="price",
                ticker="AAPL",
                at=now,
                latency_ms=42,
                status=ProviderCheckStatus.success,
                sample_count=250,
            ),
            ProviderCheck(
                id=uuid.uuid4(),
                provider="yfinance",
                tool="indicators",
                ticker="AAPL",
                at=now,
                latency_ms=85,
                status=ProviderCheckStatus.success,
                sample_count=10,
            ),
        ]
        async with session_factory() as session:
            for row in rows:
                session.add(row)
            await session.commit()

    asyncio.run(_seed())
    with TestClient(app) as client:
        response = client.get(
            "/api/data-health/calls",
            params={"provider": "yfinance", "tool": "price"},
        )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["tool"] == "price"
