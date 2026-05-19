import uuid

from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import (
    MacroBrief,
    SectorCall,
    SectorCallDirection,
    Theme,
    VerifierStatus,
)
from app.services.strategies.funnel_research.sector.prompts import (
    build_sector_messages,
)


def _macro_brief() -> MacroBrief:
    return MacroBrief(
        themes=[
            Theme(name="ai capex", evidence_ids=[uuid.uuid4()], confidence=0.8),
            Theme(name="rates plateau", evidence_ids=[], confidence=0.6),
        ],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.7,
        evidence_ids=[],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


def _sector_call() -> SectorCall:
    return SectorCall(
        sector_entity_id=uuid.uuid4(),
        sector_name="Information Technology",
        direction=SectorCallDirection.overweight,
        conviction=0.85,
        evidence_ids=[],
    )


def _chunks() -> list[EvidenceChunkRef]:
    return [
        EvidenceChunkRef(
            chunk_id=uuid.uuid4(),
            evidence_id=uuid.uuid4(),
            chunk_index=0,
            text="AAPL revenue growth at 12%",
            attributes={"source": "tiingo_news"},
        ),
        EvidenceChunkRef(
            chunk_id=uuid.uuid4(),
            evidence_id=uuid.uuid4(),
            chunk_index=0,
            text="XLK close=205.0 volume=1m",
            attributes={"source": "polygon_aggregates"},
        ),
    ]


def test_messages_include_sector_name_and_critical_block() -> None:
    messages = build_sector_messages(
        macro_brief=_macro_brief(),
        sector_call=_sector_call(),
        digest_markdown="# Sector digest\n- AAPL up",
        chunks=_chunks(),
        evidence_ids=[uuid.uuid4()],
    )
    assert messages[0].role == "system"
    assert messages[1].role == "user"
    user_text = messages[1].content
    assert "Information Technology" in user_text
    # Critical block appears at start and end (positional redundancy).
    assert user_text.count("CRITICAL:") >= 2
    assert "Output schema (strict)" in user_text


def test_messages_include_chunks_and_macro_context() -> None:
    chunks = _chunks()
    messages = build_sector_messages(
        macro_brief=_macro_brief(),
        sector_call=_sector_call(),
        digest_markdown="",
        chunks=chunks,
        evidence_ids=[],
    )
    user_text = messages[1].content
    assert "ai capex" in user_text
    assert "AAPL revenue growth at 12%" in user_text
    assert "XLK close=205.0 volume=1m" in user_text
    assert "tiingo_news" in user_text
    assert "polygon_aggregates" in user_text


def test_messages_include_sector_entity_id_for_pinning() -> None:
    call = _sector_call()
    messages = build_sector_messages(
        macro_brief=_macro_brief(),
        sector_call=call,
        digest_markdown="",
        chunks=[],
        evidence_ids=[],
    )
    assert str(call.sector_entity_id) in messages[1].content


def test_messages_include_regeneration_feedback_when_provided() -> None:
    messages = build_sector_messages(
        macro_brief=_macro_brief(),
        sector_call=_sector_call(),
        digest_markdown="",
        chunks=[],
        evidence_ids=[],
        regeneration_feedback=["quote not found in chunk"],
    )
    user_text = messages[1].content
    assert "Previous attempt rejected because" in user_text
    assert "quote not found in chunk" in user_text


def test_messages_chunks_sorted_for_determinism() -> None:
    macro_brief = _macro_brief()
    sector_call = _sector_call()
    chunks = _chunks()
    a = build_sector_messages(
        macro_brief=macro_brief,
        sector_call=sector_call,
        digest_markdown="",
        chunks=chunks,
        evidence_ids=[],
    )
    b = build_sector_messages(
        macro_brief=macro_brief,
        sector_call=sector_call,
        digest_markdown="",
        chunks=list(reversed(chunks)),
        evidence_ids=[],
    )
    assert a[1].content == b[1].content
