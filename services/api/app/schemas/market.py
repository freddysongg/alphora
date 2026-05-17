import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ScreenerUniverseEnum


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
