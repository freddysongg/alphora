import uuid

from app.schemas.macro_brief import (
    MacroBrief,
    SectorCall,
    SectorCallDirection,
    VerifierStatus,
)
from app.services.strategies.funnel_research.sector.selector import (
    MAX_SECTOR_DEEP_DIVES,
    select_sectors,
)


def _call(name: str, direction: SectorCallDirection, conviction: float) -> SectorCall:
    return SectorCall(
        sector_entity_id=uuid.uuid4(),
        sector_name=name,
        direction=direction,
        conviction=conviction,
        evidence_ids=[],
    )


def _brief_with(calls: list[SectorCall]) -> MacroBrief:
    return MacroBrief(
        themes=[],
        sector_calls=calls,
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.5,
        evidence_ids=[],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


def test_select_sectors_returns_top_three_non_neutral_by_conviction() -> None:
    brief = _brief_with(
        [
            _call("Energy", SectorCallDirection.overweight, 0.7),
            _call("Materials", SectorCallDirection.underweight, 0.9),
            _call("Industrials", SectorCallDirection.neutral, 0.95),
            _call("Health Care", SectorCallDirection.overweight, 0.8),
            _call("Financials", SectorCallDirection.underweight, 0.6),
        ]
    )
    picks = select_sectors(brief)
    assert len(picks) == MAX_SECTOR_DEEP_DIVES
    assert [call.sector_name for call in picks] == [
        "Materials",
        "Health Care",
        "Energy",
    ]


def test_select_sectors_excludes_neutral() -> None:
    brief = _brief_with(
        [
            _call("Energy", SectorCallDirection.neutral, 0.99),
            _call("Materials", SectorCallDirection.neutral, 0.98),
        ]
    )
    assert select_sectors(brief) == []


def test_select_sectors_returns_fewer_than_max_when_limited() -> None:
    brief = _brief_with(
        [
            _call("Energy", SectorCallDirection.overweight, 0.7),
            _call("Materials", SectorCallDirection.neutral, 0.95),
        ]
    )
    picks = select_sectors(brief)
    assert len(picks) == 1
    assert picks[0].sector_name == "Energy"


def test_select_sectors_ties_broken_by_name_ascending() -> None:
    brief = _brief_with(
        [
            _call("Materials", SectorCallDirection.overweight, 0.8),
            _call("Energy", SectorCallDirection.overweight, 0.8),
            _call("Health Care", SectorCallDirection.overweight, 0.8),
        ]
    )
    picks = select_sectors(brief)
    assert [call.sector_name for call in picks] == [
        "Energy",
        "Health Care",
        "Materials",
    ]


def test_select_sectors_respects_max_count_override() -> None:
    brief = _brief_with(
        [
            _call("Energy", SectorCallDirection.overweight, 0.9),
            _call("Materials", SectorCallDirection.underweight, 0.8),
            _call("Health Care", SectorCallDirection.overweight, 0.7),
        ]
    )
    picks = select_sectors(brief, max_count=2)
    assert [call.sector_name for call in picks] == ["Energy", "Materials"]
