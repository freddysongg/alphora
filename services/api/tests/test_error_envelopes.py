from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.errors import http_exception_handler, validation_exception_handler
from app.main import app


def _build_envelope_test_app() -> FastAPI:
    test_app = FastAPI()
    test_app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    test_app.add_exception_handler(RequestValidationError, validation_exception_handler)

    @test_app.get("/forbidden")
    async def _forbidden() -> None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    @test_app.get("/unauthorized")
    async def _unauthorized() -> None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    @test_app.post("/field-error")
    async def _field_error() -> None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ticker_conflict",
                "message": "ticker collides with existing run",
                "fields": {"tickers": ["already queued for trade_date"]},
            },
        )

    class _EchoPayload(BaseModel):
        name: str

    @test_app.post("/echo")
    async def _echo(payload: _EchoPayload) -> dict[str, str]:
        return {"name": payload.name}

    return test_app


def test_404_from_missing_route_returns_envelope() -> None:
    with TestClient(app) as client:
        response = client.get("/api/this-route-does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body == {"code": "http_404", "detail": "Not Found"}
    assert "fields" not in body


def test_validation_error_returns_envelope_with_fields(initialized_schema: None) -> None:
    _ = initialized_schema
    with TestClient(app) as client:
        response = client.post("/api/research-runs", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["detail"] == "Request validation failed"
    fields = body["fields"]
    assert isinstance(fields, dict)
    assert "tickers" in fields
    assert isinstance(fields["tickers"], list)
    assert fields["tickers"]


def test_403_http_exception_returns_envelope() -> None:
    test_app = _build_envelope_test_app()
    with TestClient(test_app) as client:
        response = client.get("/forbidden")
    assert response.status_code == 403
    body = response.json()
    assert body == {"code": "http_403", "detail": "forbidden"}


def test_http_exception_detail_dict_surfaces_fields() -> None:
    test_app = _build_envelope_test_app()
    with TestClient(test_app) as client:
        response = client.post("/field-error")
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "ticker_conflict"
    assert body["detail"] == "ticker collides with existing run"
    assert body["fields"] == {"tickers": ["already queued for trade_date"]}


def test_401_preserves_www_authenticate_header() -> None:
    test_app = _build_envelope_test_app()
    with TestClient(test_app) as client:
        response = client.get("/unauthorized")
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    body = response.json()
    assert body == {"code": "http_401", "detail": "not authenticated"}


def test_validation_error_field_names_use_dotted_paths() -> None:
    test_app = _build_envelope_test_app()
    payload: dict[str, Any] = {}
    with TestClient(test_app) as client:
        response = client.post("/echo", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert "name" in body["fields"]
