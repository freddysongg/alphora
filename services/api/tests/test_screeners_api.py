from typing import Any

from fastapi.testclient import TestClient

from app.main import app


def test_screener_run_creates_run_and_results(initialized_schema: None) -> None:
    _ = initialized_schema
    payload: dict[str, Any] = {
        "universe": "sp500",
        "factor_weights": {"quality": 0.4, "valuation": 0.3, "momentum": 0.3},
        "limit": 10,
    }
    with TestClient(app) as client:
        response = client.post("/api/screeners/run", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["screener_run"]["universe"] == "sp500"
    assert body["screener_run"]["result_count"] == 10
    assert len(body["results"]) == 10
    scores = [row["score"] for row in body["results"]]
    assert scores == sorted(scores, reverse=True)


def test_screener_run_rejects_unknown_factor(initialized_schema: None) -> None:
    _ = initialized_schema
    payload: dict[str, Any] = {
        "universe": "sp500",
        "factor_weights": {"unknown_factor": 0.5},
        "limit": 5,
    }
    with TestClient(app) as client:
        response = client.post("/api/screeners/run", json=payload)
    assert response.status_code == 422


def test_screener_run_requires_watchlist_id_for_watchlist_universe(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    payload: dict[str, Any] = {
        "universe": "watchlist",
        "factor_weights": {"quality": 0.5},
        "limit": 5,
    }
    with TestClient(app) as client:
        response = client.post("/api/screeners/run", json=payload)
    assert response.status_code == 422


def test_get_screener_run_returns_results(initialized_schema: None) -> None:
    _ = initialized_schema
    payload: dict[str, Any] = {
        "universe": "nasdaq100",
        "factor_weights": {"momentum": 0.6, "volatility": 0.4},
        "limit": 5,
    }
    with TestClient(app) as client:
        post_response = client.post("/api/screeners/run", json=payload)
        screener_run_id = post_response.json()["screener_run"]["id"]
        get_response = client.get(f"/api/screeners/runs/{screener_run_id}")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["screener_run"]["id"] == screener_run_id
    assert len(body["results"]) == 5


def test_get_screener_run_returns_404_when_missing(initialized_schema: None) -> None:
    _ = initialized_schema
    import uuid

    missing = uuid.uuid4()
    with TestClient(app) as client:
        response = client.get(f"/api/screeners/runs/{missing}")
    assert response.status_code == 404
