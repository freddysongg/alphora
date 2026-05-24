from __future__ import annotations

from fastapi.testclient import TestClient

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
