from fastapi.testclient import TestClient

from app import __version__
from app.main import app


def test_health_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_ready_returns_ready_when_db_reachable(initialized_schema: None) -> None:
    _ = initialized_schema
    with TestClient(app) as client:
        response = client.get("/api/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
