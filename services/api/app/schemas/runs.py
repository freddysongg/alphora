import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import (
    AnalystKindEnum,
    FinalRatingEnum,
    LlmProviderEnum,
    ProvenanceStatusEnum,
    RunEventLevelEnum,
    RunStatusEnum,
    StrategyEnum,
)

_DEFAULT_ANALYSTS: list[AnalystKindEnum] = [
    AnalystKindEnum.bull,
    AnalystKindEnum.bear,
    AnalystKindEnum.macro,
    AnalystKindEnum.fundamentals,
    AnalystKindEnum.sentiment,
    AnalystKindEnum.risk,
]


class ResearchRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, max_length=16)
    trade_date: date
    config: dict[str, object] = Field(default_factory=dict)
    strategy: StrategyEnum = StrategyEnum.tradingagents


class CreateResearchRunsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tickers: list[str] = Field(min_length=1, max_length=25)
    trade_date: date
    analysts: list[AnalystKindEnum] = Field(default_factory=lambda: list(_DEFAULT_ANALYSTS))
    llm_provider: LlmProviderEnum
    llm_model: str = Field(min_length=1, max_length=128)
    debate_depth: int = Field(default=3, ge=1, le=8)
    strategy: StrategyEnum = StrategyEnum.tradingagents

    @field_validator("tickers")
    @classmethod
    def _normalize_tickers(cls, tickers: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in tickers:
            normalized = raw.strip().upper()
            if not normalized:
                raise ValueError("ticker must not be empty")
            if len(normalized) > 16:
                raise ValueError(f"ticker {normalized!r} exceeds 16 characters")
            cleaned.append(normalized)
        return cleaned

    @field_validator("analysts")
    @classmethod
    def _ensure_non_empty(cls, analysts: list[AnalystKindEnum]) -> list[AnalystKindEnum]:
        if not analysts:
            raise ValueError("analysts must not be empty")
        return analysts


class ResearchRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticker: str
    strategy: StrategyEnum
    status: RunStatusEnum
    final_rating: FinalRatingEnum | None
    created_at: datetime
    queue_position: int | None = None


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
    strategy: StrategyEnum
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


class ResearchRunDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticker: str
    trade_date: date
    strategy: StrategyEnum
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
    reports: list[RunReportPublic]
    events: list[RunEventPublic]
    provenance: list[SourceProvenancePublic]


class GroupedRuns(BaseModel):
    queued: list[ResearchRunSummary]
    running: list[ResearchRunSummary]
    recent: list[ResearchRunSummary]
    failed: list[ResearchRunSummary]
