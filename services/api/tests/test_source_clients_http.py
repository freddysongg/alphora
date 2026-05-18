import hashlib
from dataclasses import FrozenInstanceError

import pytest


def test_source_client_error_is_exception() -> None:
    from app.services.source_clients._http import SourceClientError

    assert issubclass(SourceClientError, Exception)


def test_source_client_http_error_carries_status_and_url() -> None:
    from app.services.source_clients._http import SourceClientHTTPError

    error = SourceClientHTTPError(
        status_code=503, url="https://example.com", body_excerpt="boom"
    )

    assert error.status_code == 503
    assert error.url == "https://example.com"
    assert error.body_excerpt == "boom"


def test_source_client_timeout_error_carries_url() -> None:
    from app.services.source_clients._http import SourceClientTimeoutError

    error = SourceClientTimeoutError(url="https://example.com")

    assert error.url == "https://example.com"


def test_source_client_rate_limit_error_carries_retry_after() -> None:
    from app.services.source_clients._http import SourceClientRateLimitError

    error = SourceClientRateLimitError(
        url="https://example.com", retry_after_seconds=2.5
    )

    assert error.retry_after_seconds == pytest.approx(2.5)


def test_source_client_config_error_carries_setting_name() -> None:
    from app.services.source_clients._http import SourceClientConfigError

    error = SourceClientConfigError(setting_name="fred_api_key")

    assert error.setting_name == "fred_api_key"


def test_http_request_config_is_frozen() -> None:
    from app.services.source_clients._http import HttpRequestConfig

    config = HttpRequestConfig(method="GET", url="https://example.com")

    with pytest.raises(FrozenInstanceError):
        config.url = "https://other.com"  # type: ignore[misc]


def test_http_response_content_hash_is_sha256_hex() -> None:
    from app.services.source_clients._http import HttpResponse

    body = b"hello world"
    response = HttpResponse(
        status_code=200,
        body_bytes=body,
        headers={},
        content_hash=hashlib.sha256(body).hexdigest(),
        url="https://example.com",
    )

    assert response.content_hash == hashlib.sha256(b"hello world").hexdigest()
