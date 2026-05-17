import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import ScreenerUniverseEnum

_ALLOWED_FACTORS: frozenset[str] = frozenset(
    {"quality", "valuation", "momentum", "volatility", "sentiment"}
)
FactorKey = Literal["quality", "valuation", "momentum", "volatility", "sentiment"]


class WatchlistCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)


class WatchlistUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)


class WatchlistPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime


class WatchlistMemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watchlist_id: uuid.UUID
    ticker: str = Field(min_length=1, max_length=16)
    notes: str | None = None


class WatchlistMemberPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    watchlist_id: uuid.UUID
    ticker: str
    notes: str | None
    added_at: datetime


class ScreenerRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    universe: ScreenerUniverseEnum
    factor_weights: dict[str, float] = Field(default_factory=dict)


class ScreenerRunPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    universe: str
    factor_weights: dict[str, float]
    created_at: datetime
    finished_at: datetime | None
    result_count: int | None


class ScreenerResultPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    screener_run_id: uuid.UUID
    ticker: str
    score: float
    factor_scores: dict[str, float]


class ScreenerRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    universe: ScreenerUniverseEnum
    watchlist_id: uuid.UUID | None = None
    factor_weights: dict[str, float] = Field(default_factory=dict)
    limit: int = Field(default=50, ge=1, le=500)

    @field_validator("factor_weights")
    @classmethod
    def _validate_weights(cls, weights: dict[str, float]) -> dict[str, float]:
        for key, value in weights.items():
            if key not in _ALLOWED_FACTORS:
                raise ValueError(f"unknown factor key: {key}")
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"weight for {key} must be between 0 and 1")
        return weights

    @model_validator(mode="after")
    def _require_watchlist_when_universe_watchlist(self) -> "ScreenerRunRequest":
        if self.universe == ScreenerUniverseEnum.watchlist and self.watchlist_id is None:
            raise ValueError("watchlist_id is required when universe is 'watchlist'")
        return self


class ScreenerRunResponse(BaseModel):
    screener_run: ScreenerRunPublic
    results: list[ScreenerResultPublic]


class WatchlistMemberAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, max_length=16)
    notes: str | None = None

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, ticker: str) -> str:
        return ticker.strip().upper()


class WatchlistDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    members: list[WatchlistMemberPublic]
