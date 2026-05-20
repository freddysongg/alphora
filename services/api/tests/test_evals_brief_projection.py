"""Tests for the brief → DecisionLike projection adapter."""

import uuid

from app.schemas.company_thesis import CompanyThesis
from app.schemas.macro_brief import (
    CitedClaim,
    MacroBrief,
    SectorCall,
    SectorCallDirection,
    Theme,
    VerifierStatus,
    WatchItem,
)
from app.schemas.portfolio_brief import (
    PortfolioBrief,
    PortfolioCompanyEntry,
    PortfolioCoverage,
    PortfolioMacroSummary,
    PortfolioSectorEntry,
)
from app.schemas.sector_brief import (
    JudgeStatus,
    SectorBrief,
    SectorCompanyIdea,
)
from app.services.evals.brief_projection import (
    project_company_thesis,
    project_macro_brief,
    project_portfolio_brief,
    project_sector_brief,
)


def _evidence_id() -> uuid.UUID:
    return uuid.uuid4()


def test_project_macro_brief_emits_one_call_per_sector() -> None:
    sector_a = uuid.uuid4()
    sector_b = uuid.uuid4()
    evidence = _evidence_id()
    chunk = uuid.uuid4()
    brief = MacroBrief(
        themes=[Theme(name="t", evidence_ids=[evidence], confidence=0.5)],
        sector_calls=[
            SectorCall(
                sector_entity_id=sector_a,
                sector_name="Tech",
                direction=SectorCallDirection.overweight,
                conviction=0.8,
                evidence_ids=[evidence],
            ),
            SectorCall(
                sector_entity_id=sector_b,
                sector_name="Energy",
                direction=SectorCallDirection.underweight,
                conviction=0.6,
                evidence_ids=[evidence],
            ),
        ],
        watch_items=[WatchItem(name="w", reason="r", evidence_ids=[evidence])],
        cited_claims=[
            CitedClaim(
                claim_text="claim",
                exact_quote="the quote",
                chunk_id=chunk,
                source="src",
            )
        ],
        proposed_hypotheses=[],
        confidence=0.7,
        evidence_ids=[evidence],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )
    decision = project_macro_brief(brief)
    assert isinstance(decision["calls"], list)
    calls = decision["calls"]
    assert len(calls) == 2
    assert calls[0]["id"] == str(sector_a)
    assert calls[0]["direction"] == "overweight"
    assert calls[1]["id"] == str(sector_b)
    assert decision["top_quote"] == "the quote"


def test_project_sector_brief_uses_company_entity_id_when_available() -> None:
    sector = uuid.uuid4()
    company_a = uuid.uuid4()
    evidence = _evidence_id()
    chunk = uuid.uuid4()
    brief = SectorBrief(
        sector_entity_id=sector,
        sector_name="Tech",
        direction=SectorCallDirection.overweight,
        themes=[],
        companies=[
            SectorCompanyIdea(
                name="Apple",
                ticker="AAPL",
                direction=SectorCallDirection.overweight,
                conviction=0.8,
                evidence_ids=[evidence],
                company_entity_id=company_a,
            ),
            SectorCompanyIdea(
                name="Unmatched",
                ticker=None,
                direction=SectorCallDirection.neutral,
                conviction=0.3,
                evidence_ids=[evidence],
                company_entity_id=None,
            ),
        ],
        watch_items=[],
        cited_claims=[
            CitedClaim(
                claim_text="claim",
                exact_quote="quote",
                chunk_id=chunk,
                source="s",
            )
        ],
        confidence=0.6,
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )
    decision = project_sector_brief(brief)
    calls = decision["calls"]
    assert len(calls) == 2
    assert calls[0]["id"] == str(company_a)
    assert calls[1]["id"] == "Unmatched"
    assert decision["top_quote"] == "quote"


def test_project_company_thesis_yields_single_call() -> None:
    company = uuid.uuid4()
    sector = uuid.uuid4()
    evidence = _evidence_id()
    chunk = uuid.uuid4()
    thesis = CompanyThesis(
        company_entity_id=company,
        company_name="Apple",
        sector_entity_id=sector,
        sector_name="Tech",
        ticker="AAPL",
        direction=SectorCallDirection.overweight,
        conviction=0.8,
        bull_case="bull",
        bear_case="bear",
        catalysts=[],
        risks=[],
        cited_claims=[
            CitedClaim(
                claim_text="claim",
                exact_quote="quote",
                chunk_id=chunk,
                source="s",
            )
        ],
        confidence=0.7,
        evidence_ids=[evidence],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )
    decision = project_company_thesis(thesis)
    assert decision["calls"] == [
        {
            "id": str(company),
            "direction": "overweight",
            "conviction": 0.8,
            "evidence_ids": [str(evidence)],
        }
    ]


def test_project_portfolio_brief_prefixes_call_ids_by_kind() -> None:
    sector = uuid.uuid4()
    company = uuid.uuid4()
    brief = PortfolioBrief(
        run_id=uuid.uuid4(),
        macro=PortfolioMacroSummary(
            themes=[], watch_items=[], confidence=0.5, judge_status=JudgeStatus.passed
        ),
        sectors=[
            PortfolioSectorEntry(
                sector_entity_id=sector,
                sector_name="Tech",
                direction=SectorCallDirection.overweight,
                conviction=0.8,
                verifier_status=VerifierStatus.verified,
                judge_status=JudgeStatus.passed,
                rank=1,
            )
        ],
        companies=[
            PortfolioCompanyEntry(
                company_entity_id=company,
                company_name="Apple",
                ticker="AAPL",
                sector_entity_id=sector,
                sector_name="Tech",
                direction=SectorCallDirection.overweight,
                conviction=0.7,
                verifier_status=VerifierStatus.verified,
                judge_status=JudgeStatus.passed,
                rank=1,
            )
        ],
        cited_claims=[],
        cited_chunk_ids=[],
        coverage=PortfolioCoverage(
            sectors_selected=1,
            sectors_verified=1,
            sectors_judge_passed=1,
            sectors_judge_flagged=0,
            companies_selected=1,
            companies_verified=1,
            companies_judge_passed=1,
            companies_judge_flagged=0,
        ),
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )
    decision = project_portfolio_brief(brief)
    ids = [c["id"] for c in decision["calls"]]
    assert ids == [f"sector::{sector}", f"company::{company}"]
