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


class EntityTypeEnum(StrEnum):
    company = "company"
    person = "person"
    sector = "sector"
    country = "country"
    product = "product"
    regulator = "regulator"
    bill = "bill"
    event = "event"
    document = "document"
    instrument = "instrument"
    theme = "theme"
    hypothesis = "hypothesis"


class RelationTypeEnum(StrEnum):
    employs = "employs"
    holds_role_at = "holds_role_at"
    supplies = "supplies"
    competes_with = "competes_with"
    regulated_by = "regulated_by"
    traded_by = "traded_by"
    voted_on = "voted_on"
    sponsored = "sponsored"
    affects = "affects"
    belongs_to_sector = "belongs_to_sector"
    located_in = "located_in"
    mentioned_in = "mentioned_in"
    catalyst_for = "catalyst_for"
    derives_from_theme = "derives_from_theme"
    subsidiary_of = "subsidiary_of"
    supports_hypothesis = "supports_hypothesis"
    contradicts_hypothesis = "contradicts_hypothesis"
    validates_if_beat = "validates_if_beat"
    falsifies_if_miss = "falsifies_if_miss"


class EventResolutionKindEnum(StrEnum):
    beat = "beat"
    miss = "miss"
    neutral = "neutral"


class HypothesisStatusEnum(StrEnum):
    proposed = "proposed"
    active = "active"
    validated = "validated"
    falsified = "falsified"
    expired = "expired"
    superseded = "superseded"


class AuditActionEnum(StrEnum):
    insert = "insert"
    update = "update"
    delete = "delete"
    merge = "merge"


class EntityResolutionDecisionKindEnum(StrEnum):
    alias_match = "alias_match"
    external_id_match = "external_id_match"
    fuzzy_match = "fuzzy_match"
    llm_disambiguation = "llm_disambiguation"
    new_entity = "new_entity"


class EntityResolutionReviewStatusEnum(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    merged = "merged"


class ProposedTypeKindEnum(StrEnum):
    entity = "entity"
    relation = "relation"


class ProposedTypeStatusEnum(StrEnum):
    proposed = "proposed"
    promoted = "promoted"
    rejected = "rejected"


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
