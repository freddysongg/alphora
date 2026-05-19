import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class HypothesisStateFilter(StrEnum):
    proposed = "proposed"
    active = "active"
    all = "all"


class HypothesisState(StrEnum):
    proposed = "proposed"
    active = "active"
    validated = "validated"
    falsified = "falsified"
    expired = "expired"
    superseded = "superseded"


class HypothesisPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_text: str
    state: HypothesisState
    scope_entity_ids: list[uuid.UUID]
    scope_theme_ids: list[uuid.UUID]
    source_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class HypothesisListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[HypothesisPublic]
    next_cursor: str | None = Field(default=None)


__all__ = [
    "HypothesisListResponse",
    "HypothesisPublic",
    "HypothesisState",
    "HypothesisStateFilter",
]
