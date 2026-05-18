from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


class SourceClientError(Exception):
    """Base for all source-client errors."""


class SourceClientHTTPError(SourceClientError):
    """Non-retryable HTTP failure (4xx other than 429, or 5xx after retries)."""

    def __init__(self, *, status_code: int, url: str, body_excerpt: str) -> None:
        super().__init__(
            f"HTTP {status_code} from {url}: {body_excerpt[:200]}"
        )
        self.status_code = status_code
        self.url = url
        self.body_excerpt = body_excerpt


class SourceClientTimeoutError(SourceClientError):
    """Connect or read timeout after retries."""

    def __init__(self, *, url: str) -> None:
        super().__init__(f"timeout calling {url}")
        self.url = url


class SourceClientRateLimitError(SourceClientError):
    """429 after retries exhausted."""

    def __init__(self, *, url: str, retry_after_seconds: float | None) -> None:
        super().__init__(
            f"rate limited by {url} (retry_after={retry_after_seconds})"
        )
        self.url = url
        self.retry_after_seconds = retry_after_seconds


class SourceClientConfigError(SourceClientError):
    """Raised when a required key/setting is missing at call time."""

    def __init__(self, *, setting_name: str) -> None:
        super().__init__(f"required setting '{setting_name}' is not configured")
        self.setting_name = setting_name


@dataclass(frozen=True)
class HttpRequestConfig:
    method: Literal["GET", "POST"]
    url: str
    params: Mapping[str, str | int | float] | None = None
    headers: Mapping[str, str] | None = None
    json_body: Mapping[str, object] | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 8.0


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    body_bytes: bytes
    headers: Mapping[str, str]
    content_hash: str
    url: str
