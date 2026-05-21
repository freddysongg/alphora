import uuid

import pytest
from pydantic import ValidationError

from app.schemas.company_thesis import (
    CompanyCatalyst,
    CompanyRisk,
    CompanyThesis,
    CompanyThesisPublic,
)
from app.schemas.macro_brief import (
    CitedClaim,
    SectorCallDirection,
    VerifierStatus,
)
from app.schemas.sector_brief import JudgePublic, JudgeStatus


def _cited_claim() -> CitedClaim:
    return CitedClaim(
        claim_text="revenue accelerated",
        exact_quote="Revenue increased 25%",
        chunk_id=uuid.uuid4(),
        source="sec_edgar",
    )


def _company_thesis() -> CompanyThesis:
    return CompanyThesis(
        company_entity_id=uuid.uuid4(),
        company_name="Example Corp",
        sector_entity_id=uuid.uuid4(),
        sector_name="Information Technology",
        ticker="EXMP",
        direction=SectorCallDirection.overweight,
        conviction=0.8,
        bull_case="Demand is accelerating.",
        bear_case="Margins may compress.",
        catalysts=[
            CompanyCatalyst(
                name="earnings update",
                expected_timing="next quarter",
                evidence_ids=[uuid.uuid4()],
            )
        ],
        risks=[
            CompanyRisk(
                name="margin pressure",
                severity=0.4,
                evidence_ids=[uuid.uuid4()],
            )
        ],
        cited_claims=[_cited_claim()],
        confidence=0.7,
        evidence_ids=[uuid.uuid4()],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


def test_company_thesis_happy_path() -> None:
    thesis = _company_thesis()
    assert thesis.company_name == "Example Corp"
    assert thesis.direction is SectorCallDirection.overweight
    assert thesis.catalysts[0].expected_timing == "next quarter"


def test_company_thesis_public_round_trip() -> None:
    public = CompanyThesisPublic(
        thesis=_company_thesis(),
        judge=JudgePublic(status=JudgeStatus.not_run, reasons=[], call_id=None),
        chunks=[],
    )
    assert public.judge.status is JudgeStatus.not_run
    assert public.chunks == []


def test_company_thesis_ticker_optional() -> None:
    thesis = _company_thesis().model_copy(update={"ticker": None})
    assert thesis.ticker is None


def test_company_thesis_confidence_range() -> None:
    with pytest.raises(ValidationError):
        CompanyThesis(
            **{
                **_company_thesis().model_dump(),
                "confidence": 1.5,
            }
        )


def test_company_thesis_regeneration_count_non_negative() -> None:
    with pytest.raises(ValidationError):
        CompanyThesis(
            **{
                **_company_thesis().model_dump(),
                "regeneration_count": -1,
            }
        )


def test_company_risk_severity_range() -> None:
    with pytest.raises(ValidationError):
        CompanyRisk(name="bad risk", severity=2.0, evidence_ids=[])
