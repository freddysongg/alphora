import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import (
    AnalystKindEnum,
    FinalRatingEnum,
    ProvenanceStatusEnum,
    RunEventLevelEnum,
    RunStatusEnum,
)


class ResearchRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, max_length=16)
    trade_date: date
    config: dict[str, object] = Field(default_factory=dict)


class ResearchRunUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RunStatusEnum | None = None
    final_rating: FinalRatingEnum | None = None
    final_decision_summary: str | None = None
    wall_clock_ms: int | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ResearchRunPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticker: str
    trade_date: date
    status: RunStatusEnum
    config: dict[str, object]
    final_rating: FinalRatingEnum | None
    final_decision_summary: str | None
    wall_clock_ms: int | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RunReportPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    analyst: AnalystKindEnum
    markdown: str
    created_at: datetime


class RunEventPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    at: datetime
    level: RunEventLevelEnum
    message: str
    data: dict[str, object] | None


class SourceProvenancePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    provider: str
    tool: str
    ticker: str
    request_at: datetime
    latency_ms: int
    status: ProvenanceStatusEnum
    sample_count: int
    as_of: date | None
    error_message: str | None
