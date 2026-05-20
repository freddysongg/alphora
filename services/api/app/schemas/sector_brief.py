import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.macro_brief import (
    ChunkLookup,
    CitedClaim,
    MacroBriefPublic,
    SectorCallDirection,
    Theme,
    VerifierStatus,
    WatchItem,
)


class JudgeStatus(StrEnum):
    not_run = "not_run"
    passed = "passed"
    flagged = "flagged"


class JudgePublic(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: JudgeStatus
    reasons: list[str]
    call_id: uuid.UUID | None


class SectorCompanyIdea(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    ticker: str | None = Field(default=None, min_length=1, max_length=16)
    direction: SectorCallDirection
    conviction: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[uuid.UUID]


class SectorBrief(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sector_entity_id: uuid.UUID
    sector_name: str = Field(min_length=1, max_length=128)
    direction: SectorCallDirection
    themes: list[Theme]
    companies: list[SectorCompanyIdea]
    watch_items: list[WatchItem]
    cited_claims: list[CitedClaim]
    confidence: float = Field(ge=0.0, le=1.0)
    verifier_status: VerifierStatus
    regeneration_count: int = Field(ge=0)


class SectorBriefPublic(BaseModel):
    model_config = ConfigDict(frozen=True)

    brief: SectorBrief
    judge: JudgePublic
    chunks: list[ChunkLookup]


MacroBriefPublic.model_rebuild(
    _types_namespace={
        "JudgePublic": JudgePublic,
        "SectorBriefPublic": SectorBriefPublic,
    }
)


__all__ = [
    "JudgePublic",
    "JudgeStatus",
    "SectorBrief",
    "SectorBriefPublic",
    "SectorCompanyIdea",
]
