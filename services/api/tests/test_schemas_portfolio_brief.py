import uuid

import pytest
from pydantic import ValidationError

from app.schemas.macro_brief import (
    CitedClaim,
    SectorCallDirection,
    Theme,
    VerifierStatus,
    WatchItem,
)
from app.schemas.portfolio_brief import (
    PortfolioBrief,
    PortfolioBriefPublic,
    PortfolioCompanyEntry,
    PortfolioCoverage,
    PortfolioMacroSummary,
    PortfolioSectorEntry,
)
from app.schemas.sector_brief import JudgePublic, JudgeStatus


def _theme() -> Theme:
    return Theme(name="ai capex", evidence_ids=[uuid.uuid4()], confidence=0.7)


def _watch_item() -> WatchItem:
    return WatchItem(
        name="rate path",
        reason="watch the curve",
        evidence_ids=[uuid.uuid4()],
    )


def _cited_claim() -> CitedClaim:
    return CitedClaim(
        claim_text="capex acceleration",
        exact_quote="Capex grew 30%",
        chunk_id=uuid.uuid4(),
        source="tiingo_news",
    )


def _macro_summary() -> PortfolioMacroSummary:
    return PortfolioMacroSummary(
        themes=[_theme()],
        watch_items=[_watch_item()],
        confidence=0.65,
        judge_status=JudgeStatus.passed,
    )


def _sector_entry(rank: int = 1) -> PortfolioSectorEntry:
    return PortfolioSectorEntry(
        sector_entity_id=uuid.uuid4(),
        sector_name="Information Technology",
        direction=SectorCallDirection.overweight,
        conviction=0.8,
        verifier_status=VerifierStatus.verified,
        judge_status=JudgeStatus.passed,
        rank=rank,
    )


def _company_entry(rank: int = 1) -> PortfolioCompanyEntry:
    return PortfolioCompanyEntry(
        company_entity_id=uuid.uuid4(),
        company_name="Example Corp",
        ticker="EXMP",
        sector_entity_id=uuid.uuid4(),
        sector_name="Information Technology",
        direction=SectorCallDirection.overweight,
        conviction=0.7,
        verifier_status=VerifierStatus.verified,
        judge_status=JudgeStatus.passed,
        rank=rank,
    )


def _coverage() -> PortfolioCoverage:
    return PortfolioCoverage(
        sectors_selected=2,
        sectors_verified=2,
        sectors_judge_passed=1,
        sectors_judge_flagged=1,
        companies_selected=3,
        companies_verified=3,
        companies_judge_passed=2,
        companies_judge_flagged=1,
    )


def _portfolio_brief() -> PortfolioBrief:
    return PortfolioBrief(
        run_id=uuid.uuid4(),
        macro=_macro_summary(),
        sectors=[_sector_entry(1), _sector_entry(2)],
        companies=[_company_entry(1)],
        cited_claims=[_cited_claim()],
        cited_chunk_ids=[uuid.uuid4()],
        coverage=_coverage(),
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


def test_portfolio_brief_happy_path() -> None:
    brief = _portfolio_brief()
    assert brief.macro.confidence == 0.65
    assert brief.sectors[0].rank == 1
    assert brief.companies[0].ticker == "EXMP"
    assert brief.coverage.sectors_selected == 2


def test_portfolio_brief_public_round_trip() -> None:
    public = PortfolioBriefPublic(
        brief=_portfolio_brief(),
        judge=JudgePublic(status=JudgeStatus.not_run, reasons=[], call_id=None),
    )
    assert public.judge.status is JudgeStatus.not_run
    assert public.brief.macro.judge_status is JudgeStatus.passed


def test_portfolio_sector_entry_rank_positive() -> None:
    with pytest.raises(ValidationError):
        PortfolioSectorEntry(
            sector_entity_id=uuid.uuid4(),
            sector_name="Tech",
            direction=SectorCallDirection.overweight,
            conviction=0.5,
            verifier_status=VerifierStatus.verified,
            judge_status=JudgeStatus.passed,
            rank=0,
        )


def test_portfolio_company_entry_rank_positive() -> None:
    with pytest.raises(ValidationError):
        PortfolioCompanyEntry(
            company_entity_id=uuid.uuid4(),
            company_name="Example",
            ticker=None,
            sector_entity_id=uuid.uuid4(),
            sector_name="Tech",
            direction=SectorCallDirection.neutral,
            conviction=0.4,
            verifier_status=VerifierStatus.verified,
            judge_status=JudgeStatus.passed,
            rank=0,
        )


def test_portfolio_brief_regeneration_count_non_negative() -> None:
    with pytest.raises(ValidationError):
        PortfolioBrief(
            **{
                **_portfolio_brief().model_dump(),
                "regeneration_count": -1,
            }
        )


def test_portfolio_brief_macro_confidence_range() -> None:
    with pytest.raises(ValidationError):
        PortfolioMacroSummary(
            themes=[],
            watch_items=[],
            confidence=1.5,
            judge_status=JudgeStatus.not_run,
        )


def test_portfolio_coverage_non_negative() -> None:
    with pytest.raises(ValidationError):
        PortfolioCoverage(
            sectors_selected=-1,
            sectors_verified=0,
            sectors_judge_passed=0,
            sectors_judge_flagged=0,
            companies_selected=0,
            companies_verified=0,
            companies_judge_passed=0,
            companies_judge_flagged=0,
        )
