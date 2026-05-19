import uuid

import pytest
from pydantic import ValidationError


def test_macro_brief_scope_literal_universe() -> None:
    from app.schemas.macro_brief import MacroBriefScope

    scope = MacroBriefScope(kind="macro", universe="us_equities")
    assert scope.kind == "macro"
    with pytest.raises(ValidationError):
        MacroBriefScope(kind="macro", universe="global_equities")  # type: ignore[arg-type]


def test_theme_confidence_range() -> None:
    from app.schemas.macro_brief import Theme

    Theme(name="rates", evidence_ids=[uuid.uuid4()], confidence=0.5)
    with pytest.raises(ValidationError):
        Theme(name="rates", evidence_ids=[], confidence=1.5)
    with pytest.raises(ValidationError):
        Theme(name="rates", evidence_ids=[], confidence=-0.1)


def test_sector_call_direction_enum_and_conviction_range() -> None:
    from app.schemas.macro_brief import SectorCall, SectorCallDirection

    call = SectorCall(
        sector_entity_id=uuid.uuid4(),
        sector_name="Energy",
        direction=SectorCallDirection.overweight,
        conviction=0.8,
        evidence_ids=[],
    )
    assert call.direction is SectorCallDirection.overweight
    with pytest.raises(ValidationError):
        SectorCall(
            sector_entity_id=uuid.uuid4(),
            sector_name="Energy",
            direction="sideways",  # type: ignore[arg-type]
            conviction=0.8,
            evidence_ids=[],
        )


def test_cited_claim_requires_quote_and_chunk_id() -> None:
    from app.schemas.macro_brief import CitedClaim

    CitedClaim(
        claim_text="rates rising",
        exact_quote="Fed funds at 5.25%",
        chunk_id=uuid.uuid4(),
        source="fred",
    )
    with pytest.raises(ValidationError):
        CitedClaim(
            claim_text="x",
            exact_quote="",
            chunk_id=uuid.uuid4(),
            source="fred",
        )


def test_macro_brief_forbids_extra_fields() -> None:
    from app.schemas.macro_brief import MacroBrief, VerifierStatus

    with pytest.raises(ValidationError):
        MacroBrief(  # type: ignore[call-arg]
            themes=[],
            sector_calls=[],
            watch_items=[],
            cited_claims=[],
            proposed_hypotheses=[],
            confidence=0.5,
            evidence_ids=[],
            verifier_status=VerifierStatus.verified,
            regeneration_count=0,
            bogus_field="x",
        )


def test_macro_brief_public_wraps_brief_and_chunks() -> None:
    from app.schemas.macro_brief import (
        ChunkLookup,
        MacroBrief,
        MacroBriefPublic,
        VerifierStatus,
    )

    brief = MacroBrief(
        themes=[],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.5,
        evidence_ids=[],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )
    public = MacroBriefPublic(
        brief=brief,
        chunks=[
            ChunkLookup(
                chunk_id=uuid.uuid4(),
                evidence_id=uuid.uuid4(),
                source="fred",
                text="x",
                attributes={},
            )
        ],
    )
    assert public.brief.confidence == 0.5
    assert public.chunks[0].source == "fred"
