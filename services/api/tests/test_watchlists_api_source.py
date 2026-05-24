from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType, Hypothesis, HypothesisStatus
from app.db.models_market import Watchlist, WatchlistSource
from app.main import app


def test_create_watchlist_defaults_source_to_manual(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    with TestClient(app) as client:
        response = client.post("/api/watchlists", json={"name": "default"})
    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "manual"
    assert body["is_active"] is True
    assert body["last_built_at"] is None


def test_create_watchlist_accepts_research_source(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    with TestClient(app) as client:
        response = client.post(
            "/api/watchlists",
            json={"name": "research", "source": "research", "is_active": False},
        )
    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "research"
    assert body["is_active"] is False


def test_create_watchlist_rejects_unknown_source(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    with TestClient(app) as client:
        response = client.post(
            "/api/watchlists", json={"name": "x", "source": "llm"}
        )
    assert response.status_code == 422


def test_list_watchlists_includes_source_fields(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    with TestClient(app) as client:
        client.post("/api/watchlists", json={"name": "a"})
        client.post(
            "/api/watchlists",
            json={"name": "b", "source": "research"},
        )
        response = client.get("/api/watchlists")
    assert response.status_code == 200
    rows = response.json()
    assert {r["name"]: r["source"] for r in rows} == {
        "a": "manual",
        "b": "research",
    }


@pytest.mark.asyncio
async def test_rebuild_research_endpoint_populates_members(
    db_session: AsyncSession,
) -> None:
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.company.value,
        canonical_name="NVDA",
        ticker_normalized="NVDA",
    )
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name="research",
        source=WatchlistSource.research.value,
    )
    hypothesis = Hypothesis(
        id=uuid.uuid4(),
        claim_text="ai chips beat estimates",
        scope_entity_ids=[str(entity.id)],
        status=HypothesisStatus.active.value,
        belief=0.85,
        last_activity_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add_all([entity, watchlist, hypothesis])
    await db_session.commit()

    with TestClient(app) as client:
        response = client.post(
            f"/api/watchlists/{watchlist.id}/rebuild-research",
            json={"evidence_window_hours": 24, "min_belief": 0.6, "max_tickers": 10},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 1
    detail_response = TestClient(app).get(f"/api/watchlists/{watchlist.id}")
    detail = detail_response.json()
    assert [m["ticker"] for m in detail["members"]] == ["NVDA"]
    assert detail["last_built_at"] is not None


@pytest.mark.asyncio
async def test_rebuild_research_endpoint_rejects_manual_watchlist(
    db_session: AsyncSession,
) -> None:
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name="manual",
        source=WatchlistSource.manual.value,
    )
    db_session.add(watchlist)
    await db_session.commit()
    with TestClient(app) as client:
        response = client.post(
            f"/api/watchlists/{watchlist.id}/rebuild-research",
            json={"evidence_window_hours": 24, "min_belief": 0.6, "max_tickers": 10},
        )
    assert response.status_code == 400
    assert "manual" in response.json()["detail"].lower()


def test_rebuild_research_endpoint_404_when_watchlist_missing(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    missing = uuid.uuid4()
    with TestClient(app) as client:
        response = client.post(
            f"/api/watchlists/{missing}/rebuild-research",
            json={"evidence_window_hours": 24, "min_belief": 0.6, "max_tickers": 10},
        )
    assert response.status_code == 404
