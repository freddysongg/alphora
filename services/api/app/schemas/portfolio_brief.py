import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.macro_brief import (
    CitedClaim,
    SectorCallDirection,
    Theme,
    VerifierStatus,
    WatchItem,
)
from app.schemas.sector_brief import JudgePublic, JudgeStatus


class PortfolioMacroSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    themes: list[Theme]
    watch_items: list[WatchItem]
    confidence: float = Field(ge=0.0, le=1.0)
    judge_status: JudgeStatus


class PortfolioSectorEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sector_entity_id: uuid.UUID
    sector_name: str = Field(min_length=1, max_length=128)
    direction: SectorCallDirection
    conviction: float = Field(ge=0.0, le=1.0)
    verifier_status: VerifierStatus
    judge_status: JudgeStatus
    rank: int = Field(ge=1)


class PortfolioCompanyEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    company_entity_id: uuid.UUID
    company_name: str = Field(min_length=1, max_length=200)
    ticker: str | None = Field(default=None, min_length=1, max_length=16)
    sector_entity_id: uuid.UUID
    sector_name: str = Field(min_length=1, max_length=128)
    direction: SectorCallDirection
    conviction: float = Field(ge=0.0, le=1.0)
    verifier_status: VerifierStatus
    judge_status: JudgeStatus
    rank: int = Field(ge=1)


class PortfolioCoverage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sectors_selected: int = Field(ge=0)
    sectors_verified: int = Field(ge=0)
    sectors_judge_passed: int = Field(ge=0)
    sectors_judge_flagged: int = Field(ge=0)
    companies_selected: int = Field(ge=0)
    companies_verified: int = Field(ge=0)
    companies_judge_passed: int = Field(ge=0)
    companies_judge_flagged: int = Field(ge=0)


class PortfolioBrief(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: uuid.UUID
    macro: PortfolioMacroSummary
    sectors: list[PortfolioSectorEntry]
    companies: list[PortfolioCompanyEntry]
    cited_claims: list[CitedClaim]
    cited_chunk_ids: list[uuid.UUID]
    coverage: PortfolioCoverage
    verifier_status: VerifierStatus
    regeneration_count: int = Field(ge=0)


class PortfolioBriefPublic(BaseModel):
    model_config = ConfigDict(frozen=True)

    brief: PortfolioBrief
    judge: JudgePublic


__all__ = [
    "PortfolioBrief",
    "PortfolioBriefPublic",
    "PortfolioCompanyEntry",
    "PortfolioCoverage",
    "PortfolioMacroSummary",
    "PortfolioSectorEntry",
]
