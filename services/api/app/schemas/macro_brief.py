import uuid
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MacroBriefScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["macro"]
    universe: Literal["us_equities"]


class Theme(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    evidence_ids: list[uuid.UUID]
    confidence: float = Field(ge=0.0, le=1.0)


class SectorCallDirection(StrEnum):
    overweight = "overweight"
    underweight = "underweight"
    neutral = "neutral"


class SectorCall(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sector_entity_id: uuid.UUID
    sector_name: str = Field(min_length=1, max_length=64)
    direction: SectorCallDirection
    conviction: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[uuid.UUID]


class WatchItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    reason: str
    evidence_ids: list[uuid.UUID]


class CitedClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_text: str
    exact_quote: str = Field(min_length=1)
    chunk_id: uuid.UUID
    source: str = Field(min_length=1, max_length=64)


class ProposedHypothesis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_text: str
    scope_entity_ids: list[uuid.UUID]
    evidence_ids: list[uuid.UUID]


class VerifierStatus(StrEnum):
    verified = "verified"
    quote_unverified = "quote_unverified"


class MacroBrief(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    themes: list[Theme]
    sector_calls: list[SectorCall]
    watch_items: list[WatchItem]
    cited_claims: list[CitedClaim]
    proposed_hypotheses: list[ProposedHypothesis]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[uuid.UUID]
    verifier_status: VerifierStatus
    regeneration_count: int = Field(ge=0)


class ChunkLookup(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: uuid.UUID
    evidence_id: uuid.UUID
    source: str
    text: str
    attributes: dict[str, object]


class MacroBriefPublic(BaseModel):
    model_config = ConfigDict(frozen=True)

    brief: MacroBrief
    chunks: list[ChunkLookup]


__all__ = [
    "ChunkLookup",
    "CitedClaim",
    "MacroBrief",
    "MacroBriefPublic",
    "MacroBriefScope",
    "ProposedHypothesis",
    "SectorCall",
    "SectorCallDirection",
    "Theme",
    "VerifierStatus",
    "WatchItem",
]
