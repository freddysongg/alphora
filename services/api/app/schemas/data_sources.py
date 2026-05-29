import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_LOOKBACK_DAYS: tuple[int, ...] = (7, 30, 90, 365)
TICKER_PATTERN: str = r"^[A-Z][A-Z0-9.\-]{0,15}$"
_TICKER_RE: re.Pattern[str] = re.compile(TICKER_PATTERN)

DataSourceScope = Literal["ticker", "macro"]
ApiKeyStatus = Literal["configured", "missing", "n/a"]
TestPullStatus = Literal["ok", "error"]


class DataSourceSettingsPublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    lookback_days: int | None
    notes: str | None
    updated_at: datetime | None


class DataSourceEntryPublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    provider: str
    label: str
    caption: str
    scope: DataSourceScope
    default_lookback_days: int | None
    api_key_env: str | None
    api_key_status: ApiKeyStatus
    preview_columns: tuple[str, ...]
    settings: DataSourceSettingsPublic


class DataSourceList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[DataSourceEntryPublic]


class DataSourceSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    lookback_days: int | None = Field(default=None)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("lookback_days")
    @classmethod
    def _validate_lookback(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value not in ALLOWED_LOOKBACK_DAYS:
            raise ValueError(f"lookback_days must be one of {ALLOWED_LOOKBACK_DAYS}")
        return value


class DataSourceTestPullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str | None = Field(default=None, max_length=16)
    lookback_days: int | None = None

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str | None) -> str | None:
        if value is None:
            return None
        upper = value.strip().upper()
        if not _TICKER_RE.match(upper):
            raise ValueError("ticker does not match required pattern")
        return upper

    @field_validator("lookback_days")
    @classmethod
    def _validate_lookback(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value not in ALLOWED_LOOKBACK_DAYS:
            raise ValueError(f"lookback_days must be one of {ALLOWED_LOOKBACK_DAYS}")
        return value


class TestPullError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    detail: str


class DataSourceTestPullResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_key: str
    status: TestPullStatus
    latency_ms: int
    count: int
    as_of: datetime | None
    preview: list[dict[str, object]]
    raw: str | None
    error: TestPullError | None
