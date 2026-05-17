from fastapi.testclient import TestClient

from app.main import app


def test_list_watchlists_returns_empty(initialized_schema: None) -> None:
    _ = initialized_schema
    with TestClient(app) as client:
        response = client.get("/api/watchlists")
    assert response.status_code == 200
    assert response.json() == []


def test_create_watchlist_and_fetch_detail(initialized_schema: None) -> None:
    _ = initialized_schema
    with TestClient(app) as client:
        create = client.post("/api/watchlists", json={"name": "AI watch"})
        assert create.status_code == 201
        watchlist_id = create.json()["id"]
        detail = client.get(f"/api/watchlists/{watchlist_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["name"] == "AI watch"
    assert body["members"] == []


def test_add_and_remove_watchlist_member(initialized_schema: None) -> None:
    _ = initialized_schema
    with TestClient(app) as client:
        create = client.post("/api/watchlists", json={"name": "AI watch"})
        watchlist_id = create.json()["id"]
        add = client.post(
            f"/api/watchlists/{watchlist_id}/members",
            json={"ticker": "nvda", "notes": "AI accel"},
        )
        assert add.status_code == 201, add.text
        assert add.json()["ticker"] == "NVDA"
        assert add.json()["notes"] == "AI accel"
        detail = client.get(f"/api/watchlists/{watchlist_id}")
        assert len(detail.json()["members"]) == 1
        remove = client.delete(f"/api/watchlists/{watchlist_id}/members/NVDA")
        assert remove.status_code == 204
        detail_after = client.get(f"/api/watchlists/{watchlist_id}")
        assert detail_after.json()["members"] == []


def test_add_duplicate_member_returns_409(initialized_schema: None) -> None:
    _ = initialized_schema
    with TestClient(app) as client:
        create = client.post("/api/watchlists", json={"name": "AI watch"})
        watchlist_id = create.json()["id"]
        client.post(
            f"/api/watchlists/{watchlist_id}/members", json={"ticker": "NVDA"}
        )
        duplicate = client.post(
            f"/api/watchlists/{watchlist_id}/members", json={"ticker": "NVDA"}
        )
    assert duplicate.status_code == 409


def test_remove_unknown_member_returns_404(initialized_schema: None) -> None:
    _ = initialized_schema
    with TestClient(app) as client:
        create = client.post("/api/watchlists", json={"name": "AI watch"})
        watchlist_id = create.json()["id"]
        remove = client.delete(f"/api/watchlists/{watchlist_id}/members/AAPL")
    assert remove.status_code == 404
