import uuid

from app.schemas.macro_brief import SectorCallDirection, VerifierStatus
from app.schemas.sector_brief import (
    JudgePublic,
    JudgeStatus,
    SectorBrief,
    SectorBriefPublic,
    SectorCompanyIdea,
)
from app.services.strategies.funnel_research.company.selector import (
    MAX_COMPANY_DEEP_DIVES,
    select_companies,
)


def _company(
    name: str,
    *,
    ticker: str | None,
    direction: SectorCallDirection,
    conviction: float,
) -> SectorCompanyIdea:
    return SectorCompanyIdea(
        name=name,
        ticker=ticker,
        direction=direction,
        conviction=conviction,
        evidence_ids=[uuid.uuid4()],
    )


def _sector_public(
    sector_name: str,
    *,
    companies: list[SectorCompanyIdea],
) -> SectorBriefPublic:
    return SectorBriefPublic(
        brief=SectorBrief(
            sector_entity_id=uuid.uuid4(),
            sector_name=sector_name,
            direction=SectorCallDirection.overweight,
            themes=[],
            companies=companies,
            watch_items=[],
            cited_claims=[],
            confidence=0.7,
            verifier_status=VerifierStatus.verified,
            regeneration_count=0,
        ),
        judge=JudgePublic(status=JudgeStatus.not_run, reasons=[], call_id=None),
        chunks=[],
    )


def test_select_companies_returns_empty_for_no_sector_briefs() -> None:
    assert select_companies([]) == []


def test_select_companies_excludes_neutral_company_ideas() -> None:
    sector = _sector_public(
        "Energy",
        companies=[
            _company(
                "Neutral Co",
                ticker="NEU",
                direction=SectorCallDirection.neutral,
                conviction=0.99,
            )
        ],
    )

    assert select_companies([sector]) == []


def test_select_companies_orders_by_conviction_then_sector_then_index() -> None:
    energy = _sector_public(
        "Energy",
        companies=[
            _company(
                "Energy B",
                ticker="ENB",
                direction=SectorCallDirection.overweight,
                conviction=0.8,
            ),
            _company(
                "Energy A",
                ticker="ENA",
                direction=SectorCallDirection.underweight,
                conviction=0.8,
            ),
        ],
    )
    technology = _sector_public(
        "Information Technology",
        companies=[
            _company(
                "Tech A",
                ticker="TCA",
                direction=SectorCallDirection.overweight,
                conviction=0.9,
            ),
            _company(
                "Tech B",
                ticker="TCB",
                direction=SectorCallDirection.overweight,
                conviction=0.8,
            ),
        ],
    )

    selected = select_companies([technology, energy], max_count=4)

    assert [idea.company_name for idea in selected] == [
        "Tech A",
        "Energy B",
        "Energy A",
        "Tech B",
    ]
    assert selected[0].ticker == "TCA"
    assert selected[1].sector_name == "Energy"
    assert selected[1].sector_company_index == 0


def test_select_companies_respects_default_cap() -> None:
    sector = _sector_public(
        "Energy",
        companies=[
            _company(
                f"Company {index}",
                ticker=f"C{index}",
                direction=SectorCallDirection.overweight,
                conviction=1.0 - (index * 0.01),
            )
            for index in range(MAX_COMPANY_DEEP_DIVES + 2)
        ],
    )

    selected = select_companies([sector])

    assert len(selected) == MAX_COMPANY_DEEP_DIVES
    assert selected[-1].company_name == f"Company {MAX_COMPANY_DEEP_DIVES - 1}"


def test_select_companies_deduplicates_by_uppercase_ticker() -> None:
    sector = _sector_public(
        "Information Technology",
        companies=[
            _company(
                "Example Better",
                ticker="exmp",
                direction=SectorCallDirection.overweight,
                conviction=0.9,
            ),
            _company(
                "Example Duplicate",
                ticker="EXMP",
                direction=SectorCallDirection.overweight,
                conviction=0.8,
            ),
        ],
    )

    selected = select_companies([sector])

    assert [idea.company_name for idea in selected] == ["Example Better"]
    assert selected[0].ticker == "EXMP"


def test_select_companies_deduplicates_by_normalized_name_without_ticker() -> None:
    sector = _sector_public(
        "Health Care",
        companies=[
            _company(
                "Cafe Therapeutics",
                ticker=None,
                direction=SectorCallDirection.overweight,
                conviction=0.9,
            ),
            _company(
                "Cafe   Therapeutics",
                ticker=None,
                direction=SectorCallDirection.underweight,
                conviction=0.8,
            ),
        ],
    )

    selected = select_companies([sector])

    assert [idea.company_name for idea in selected] == ["Cafe Therapeutics"]


def test_select_companies_returns_empty_when_max_count_is_zero() -> None:
    sector = _sector_public(
        "Energy",
        companies=[
            _company(
                "Energy Co",
                ticker="ENRG",
                direction=SectorCallDirection.overweight,
                conviction=0.9,
            )
        ],
    )

    assert select_companies([sector], max_count=0) == []
