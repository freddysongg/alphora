"""Deterministic portfolio brief aggregator.

Rolls up the verified macro brief, persisted sector briefs, and persisted
company theses into a single research summary. No LLM synthesis happens
here: citations are inherited from upstream briefs that were already
verified. The LLM judge is re-applied as advisory downstream in the
runner.

Ranking rules (sectors and companies):

1. Non-neutral directions before neutral.
2. Judge status priority: passed > flagged > not_run.
3. Conviction descending.
4. Lexicographic sector_name ascending, then company_name ascending.

The aggregator is pure: it takes typed inputs and returns a `PortfolioBrief`
schema. Persistence and judge invocation live in `runner.py`.
"""
from __future__ import annotations

import uuid

from app.schemas.company_thesis import CompanyThesisPublic
from app.schemas.macro_brief import (
    CitedClaim,
    MacroBrief,
    SectorCallDirection,
    VerifierStatus,
)
from app.schemas.portfolio_brief import (
    PortfolioBrief,
    PortfolioCompanyEntry,
    PortfolioCoverage,
    PortfolioMacroSummary,
    PortfolioSectorEntry,
)
from app.schemas.sector_brief import JudgePublic, JudgeStatus, SectorBriefPublic

_DIRECTION_RANK = {
    SectorCallDirection.overweight: 0,
    SectorCallDirection.underweight: 0,
    SectorCallDirection.neutral: 1,
}

_JUDGE_RANK = {
    JudgeStatus.passed: 0,
    JudgeStatus.flagged: 1,
    JudgeStatus.not_run: 2,
}


def _macro_summary(*, macro: MacroBrief, macro_judge: JudgePublic) -> PortfolioMacroSummary:
    return PortfolioMacroSummary(
        themes=list(macro.themes),
        watch_items=list(macro.watch_items),
        confidence=macro.confidence,
        judge_status=macro_judge.status,
    )


def _sector_entries(
    sectors: list[SectorBriefPublic],
) -> list[PortfolioSectorEntry]:
    keyed = [
        (
            _DIRECTION_RANK[item.brief.direction],
            _JUDGE_RANK[item.judge.status],
            -item.brief.confidence,
            item.brief.sector_name.casefold(),
            item,
        )
        for item in sectors
    ]
    keyed.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    return [
        PortfolioSectorEntry(
            sector_entity_id=item.brief.sector_entity_id,
            sector_name=item.brief.sector_name,
            direction=item.brief.direction,
            conviction=item.brief.confidence,
            verifier_status=item.brief.verifier_status,
            judge_status=item.judge.status,
            rank=index + 1,
        )
        for index, (_, _, _, _, item) in enumerate(keyed)
    ]


def _company_entries(
    companies: list[CompanyThesisPublic],
) -> list[PortfolioCompanyEntry]:
    keyed = [
        (
            _DIRECTION_RANK[item.thesis.direction],
            _JUDGE_RANK[item.judge.status],
            -item.thesis.conviction,
            item.thesis.sector_name.casefold(),
            item.thesis.company_name.casefold(),
            item,
        )
        for item in companies
    ]
    keyed.sort(key=lambda row: (row[0], row[1], row[2], row[3], row[4]))
    return [
        PortfolioCompanyEntry(
            company_entity_id=item.thesis.company_entity_id,
            company_name=item.thesis.company_name,
            ticker=item.thesis.ticker,
            sector_entity_id=item.thesis.sector_entity_id,
            sector_name=item.thesis.sector_name,
            direction=item.thesis.direction,
            conviction=item.thesis.conviction,
            verifier_status=item.thesis.verifier_status,
            judge_status=item.judge.status,
            rank=index + 1,
        )
        for index, (_, _, _, _, _, item) in enumerate(keyed)
    ]


def _coverage(
    *,
    sectors: list[SectorBriefPublic],
    companies: list[CompanyThesisPublic],
) -> PortfolioCoverage:
    return PortfolioCoverage(
        sectors_selected=len(sectors),
        sectors_verified=sum(
            1
            for item in sectors
            if item.brief.verifier_status is VerifierStatus.verified
        ),
        sectors_judge_passed=sum(
            1 for item in sectors if item.judge.status is JudgeStatus.passed
        ),
        sectors_judge_flagged=sum(
            1 for item in sectors if item.judge.status is JudgeStatus.flagged
        ),
        companies_selected=len(companies),
        companies_verified=sum(
            1
            for item in companies
            if item.thesis.verifier_status is VerifierStatus.verified
        ),
        companies_judge_passed=sum(
            1 for item in companies if item.judge.status is JudgeStatus.passed
        ),
        companies_judge_flagged=sum(
            1 for item in companies if item.judge.status is JudgeStatus.flagged
        ),
    )


def _collate_cited_claims(
    *,
    macro: MacroBrief,
    sectors: list[SectorBriefPublic],
    companies: list[CompanyThesisPublic],
) -> tuple[list[CitedClaim], list[uuid.UUID]]:
    seen_keys: set[tuple[uuid.UUID, str]] = set()
    claims: list[CitedClaim] = []
    seen_chunk_ids: set[uuid.UUID] = set()
    chunk_ids: list[uuid.UUID] = []

    def _add(claim: CitedClaim) -> None:
        key = (claim.chunk_id, claim.exact_quote)
        if key not in seen_keys:
            seen_keys.add(key)
            claims.append(claim)
        if claim.chunk_id not in seen_chunk_ids:
            seen_chunk_ids.add(claim.chunk_id)
            chunk_ids.append(claim.chunk_id)

    for claim in macro.cited_claims:
        _add(claim)
    for sector in sectors:
        for claim in sector.brief.cited_claims:
            _add(claim)
    for company in companies:
        for claim in company.thesis.cited_claims:
            _add(claim)
    return claims, chunk_ids


def aggregate_portfolio(
    *,
    run_id: uuid.UUID,
    macro: MacroBrief,
    macro_judge: JudgePublic,
    sectors: list[SectorBriefPublic],
    companies: list[CompanyThesisPublic],
) -> PortfolioBrief:
    cited_claims, cited_chunk_ids = _collate_cited_claims(
        macro=macro, sectors=sectors, companies=companies
    )
    return PortfolioBrief(
        run_id=run_id,
        macro=_macro_summary(macro=macro, macro_judge=macro_judge),
        sectors=_sector_entries(sectors),
        companies=_company_entries(companies),
        cited_claims=cited_claims,
        cited_chunk_ids=cited_chunk_ids,
        coverage=_coverage(sectors=sectors, companies=companies),
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


__all__ = ["aggregate_portfolio"]
