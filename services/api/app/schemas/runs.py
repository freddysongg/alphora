import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import (
    AnalystKindEnum,
    FinalRatingEnum,
    LlmProviderEnum,
    ProvenanceStatusEnum,
    RunEventLevelEnum,
    RunStatusEnum,
    StrategyEnum,
)
from app.schemas.macro_brief import MacroBriefScope

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

    strategy: StrategyEnum = StrategyEnum.tradingagents
    trade_date: date
    tickers: list[str] | None = Field(default=None, min_length=1, max_length=25)
    scope_payload: MacroBriefScope | None = None
    analysts: list[AnalystKindEnum] = Field(default_factory=lambda: list(_DEFAULT_ANALYSTS))
    llm_provider: LlmProviderEnum | None = None
    llm_model: str | None = Field(default=None, min_length=1, max_length=128)
    debate_depth: int = Field(default=3, ge=1, le=8)

    @field_validator("tickers")
    @classmethod
    def _normalize_tickers(cls, tickers: list[str] | None) -> list[str] | None:
        if tickers is None:
            return None
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

    @model_validator(mode="after")
    def _validate_strategy_branch(self) -> Self:
        if self.strategy is StrategyEnum.tradingagents:
            if not self.tickers:
                raise ValueError("tradingagents strategy requires tickers")
            if self.scope_payload is not None:
                raise ValueError("scope_payload is only valid for funnel_research")
            if self.llm_provider is None or self.llm_model is None:
                raise ValueError(
                    "tradingagents strategy requires llm_provider and llm_model"
                )
        elif self.strategy is StrategyEnum.funnel_research:
            if self.tickers:
                raise ValueError("funnel_research strategy does not accept tickers")
            if self.scope_payload is None:
                raise ValueError("funnel_research strategy requires scope_payload")
        return self


class ResearchRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticker: str | None
    strategy: StrategyEnum
    status: RunStatusEnum
    final_rating: FinalRatingEnum | None
    created_at: datetime
    queue_position: int | None = None
    scope_payload: dict[str, object] | None = None


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
    ticker: str | None
    trade_date: date
    strategy: StrategyEnum
    status: RunStatusEnum
    config: dict[str, object]
    scope_payload: dict[str, object] | None = None
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
    ticker: str | None
    trade_date: date
    strategy: StrategyEnum
    status: RunStatusEnum
    config: dict[str, object]
    scope_payload: dict[str, object] | None = None
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
    cancelled: list[ResearchRunSummary]
