import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.macro_brief import (
    ChunkLookup,
    CitedClaim,
    SectorCallDirection,
    VerifierStatus,
)
from app.schemas.sector_brief import JudgePublic


class CompanyCatalyst(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    expected_timing: str | None = Field(default=None, min_length=1, max_length=120)
    evidence_ids: list[uuid.UUID]


class CompanyRisk(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    severity: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[uuid.UUID]


class CompanyThesis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    company_entity_id: uuid.UUID
    company_name: str = Field(min_length=1, max_length=200)
    sector_entity_id: uuid.UUID
    sector_name: str = Field(min_length=1, max_length=128)
    ticker: str | None = Field(default=None, min_length=1, max_length=16)
    direction: SectorCallDirection
    conviction: float = Field(ge=0.0, le=1.0)
    bull_case: str = Field(min_length=1)
    bear_case: str = Field(min_length=1)
    catalysts: list[CompanyCatalyst]
    risks: list[CompanyRisk]
    cited_claims: list[CitedClaim]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[uuid.UUID]
    verifier_status: VerifierStatus
    regeneration_count: int = Field(ge=0)


class CompanyThesisPublic(BaseModel):
    model_config = ConfigDict(frozen=True)

    thesis: CompanyThesis
    judge: JudgePublic
    chunks: list[ChunkLookup]


__all__ = [
    "CompanyCatalyst",
    "CompanyRisk",
    "CompanyThesis",
    "CompanyThesisPublic",
]
