from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RunStatusEnum(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    paused = "paused"


class StrategyEnum(StrEnum):
    tradingagents = "tradingagents"
    funnel_research = "funnel_research"


class FinalRatingEnum(StrEnum):
    buy = "buy"
    hold = "hold"
    sell = "sell"
    none_ = "none"


class AnalystKindEnum(StrEnum):
    bull = "bull"
    bear = "bear"
    macro = "macro"
    fundamentals = "fundamentals"
    sentiment = "sentiment"
    risk = "risk"


class RunEventLevelEnum(StrEnum):
    info = "info"
    warn = "warn"
    err = "err"


class ProvenanceStatusEnum(StrEnum):
    success = "success"
    failure = "failure"
    partial = "partial"


class OrderSideEnum(StrEnum):
    buy = "buy"
    sell = "sell"


class OrderTypeEnum(StrEnum):
    market = "market"


class OrderStatusEnum(StrEnum):
    pending = "pending"
    accepted = "accepted"
    filled = "filled"
    cancelled = "cancelled"
    rejected = "rejected"


class ProviderCheckStatusEnum(StrEnum):
    success = "success"
    failure = "failure"
    partial = "partial"


class LlmProviderEnum(StrEnum):
    openai = "openai"
    anthropic = "anthropic"
    together = "together"


class ScreenerUniverseEnum(StrEnum):
    sp500 = "sp500"
    nasdaq100 = "nasdaq100"
    watchlist = "watchlist"


class PaginationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class Page[T](BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    details: dict[str, object] | None = None
