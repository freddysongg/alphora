from typing import Any

from fastapi.testclient import TestClient

from app.main import app


def test_get_settings_auto_creates_singleton(initialized_schema: None) -> None:
    _ = initialized_schema
    with TestClient(app) as client:
        response = client.get("/api/settings/providers")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 1
    assert body["llm_provider"] == "openai"
    assert body["has_llm_api_key"] is False
    assert body["llm_api_key_masked"] is None


def test_update_settings_masks_secrets_on_response(initialized_schema: None) -> None:
    _ = initialized_schema
    payload: dict[str, Any] = {
        "llm_provider": "anthropic",
        "llm_model": "claude-3-5-sonnet",
        "llm_api_key": "sk-test-abcd1234",
        "alpha_vantage_key": "av-XYZ789",
        "default_depth": 5,
    }
    with TestClient(app) as client:
        put_response = client.put("/api/settings/providers", json=payload)
        get_response = client.get("/api/settings/providers")
    assert put_response.status_code == 200
    put_body = put_response.json()
    assert put_body["llm_provider"] == "anthropic"
    assert put_body["llm_model"] == "claude-3-5-sonnet"
    assert put_body["default_depth"] == 5
    assert put_body["has_llm_api_key"] is True
    assert put_body["has_alpha_vantage_key"] is True
    assert put_body["llm_api_key_masked"] == "***1234"
    assert put_body["alpha_vantage_key_masked"] == "***Z789"
    assert "llm_api_key" not in put_body
    assert "alpha_vantage_key" not in put_body
    assert "llm_api_key_encrypted" not in put_body

    get_body = get_response.json()
    assert get_body["llm_api_key_masked"] == "***1234"
    assert get_body["has_llm_api_key"] is True
