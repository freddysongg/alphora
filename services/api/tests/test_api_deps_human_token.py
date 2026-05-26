"""Unit tests for verify_human_token: 503 / 401 / pass."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import HumanTokenDep


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.post("/echo")
    async def echo(identity: HumanTokenDep) -> dict[str, str]:
        return {"identity": identity}

    return app


def test_verify_human_token_503_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("HUMAN_APPROVAL_TOKEN", "")
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/echo", headers={"X-Human-Token": "anything"})
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"].lower()
    get_settings.cache_clear()


def test_verify_human_token_401_when_missing_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("HUMAN_APPROVAL_TOKEN", "the-real-token-32chars-ok-xxxxxx")
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/echo")
    assert resp.status_code == 401
    get_settings.cache_clear()


def test_verify_human_token_401_when_mismatched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("HUMAN_APPROVAL_TOKEN", "the-real-token-32chars-ok-xxxxxx")
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/echo", headers={"X-Human-Token": "wrong"})
    assert resp.status_code == 401
    get_settings.cache_clear()


def test_verify_human_token_returns_identity_when_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("HUMAN_APPROVAL_TOKEN", "the-real-token-32chars-ok-xxxxxx")
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/echo", headers={"X-Human-Token": "the-real-token-32chars-ok-xxxxxx"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"identity": "human:default"}
    get_settings.cache_clear()
