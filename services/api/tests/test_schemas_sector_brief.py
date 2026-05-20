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
from app.schemas.sector_brief import (
    JudgePublic,
    JudgeStatus,
    SectorBrief,
    SectorBriefPublic,
    SectorCompanyIdea,
)


def _make_theme() -> Theme:
    return Theme(name="ai capex", evidence_ids=[uuid.uuid4()], confidence=0.7)


def _make_cited_claim() -> CitedClaim:
    return CitedClaim(
        claim_text="hyperscaler capex is up",
        exact_quote="capex up 30%",
        chunk_id=uuid.uuid4(),
        source="tiingo_news",
    )


def _make_company() -> SectorCompanyIdea:
    return SectorCompanyIdea(
        name="ExampleCo",
        ticker="EXMP",
        direction=SectorCallDirection.overweight,
        conviction=0.6,
        evidence_ids=[uuid.uuid4()],
    )


def test_sector_brief_happy_path() -> None:
    sector_id = uuid.uuid4()
    brief = SectorBrief(
        sector_entity_id=sector_id,
        sector_name="Information Technology",
        direction=SectorCallDirection.overweight,
        themes=[_make_theme()],
        companies=[_make_company()],
        watch_items=[
            WatchItem(name="data center supply", reason="bottleneck", evidence_ids=[])
        ],
        cited_claims=[_make_cited_claim()],
        confidence=0.7,
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )
    assert brief.sector_entity_id == sector_id
    assert brief.companies[0].direction is SectorCallDirection.overweight


def test_sector_brief_confidence_range() -> None:
    with pytest.raises(ValidationError):
        SectorBrief(
            sector_entity_id=uuid.uuid4(),
            sector_name="Information Technology",
            direction=SectorCallDirection.overweight,
            themes=[],
            companies=[],
            watch_items=[],
            cited_claims=[],
            confidence=1.5,
            verifier_status=VerifierStatus.verified,
            regeneration_count=0,
        )


def test_sector_brief_regeneration_count_non_negative() -> None:
    with pytest.raises(ValidationError):
        SectorBrief(
            sector_entity_id=uuid.uuid4(),
            sector_name="Information Technology",
            direction=SectorCallDirection.overweight,
            themes=[],
            companies=[],
            watch_items=[],
            cited_claims=[],
            confidence=0.5,
            verifier_status=VerifierStatus.verified,
            regeneration_count=-1,
        )


def test_judge_public_status_enum() -> None:
    judge = JudgePublic(status=JudgeStatus.passed, reasons=[], call_id=uuid.uuid4())
    assert judge.status is JudgeStatus.passed


def test_judge_public_not_run_allows_null_call_id() -> None:
    judge = JudgePublic(status=JudgeStatus.not_run, reasons=[], call_id=None)
    assert judge.call_id is None


def test_sector_company_idea_ticker_optional() -> None:
    company = SectorCompanyIdea(
        name="NoTicker Inc",
        ticker=None,
        direction=SectorCallDirection.neutral,
        conviction=0.4,
        evidence_ids=[],
    )
    assert company.ticker is None


def test_sector_brief_public_round_trip() -> None:
    public = SectorBriefPublic(
        brief=SectorBrief(
            sector_entity_id=uuid.uuid4(),
            sector_name="Energy",
            direction=SectorCallDirection.neutral,
            themes=[],
            companies=[],
            watch_items=[],
            cited_claims=[],
            confidence=0.5,
            verifier_status=VerifierStatus.verified,
            regeneration_count=0,
        ),
        judge=JudgePublic(status=JudgeStatus.not_run, reasons=[], call_id=None),
        chunks=[],
    )
    assert public.judge.status is JudgeStatus.not_run
    assert public.chunks == []
