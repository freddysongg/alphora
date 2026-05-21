import uuid

from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import SectorCallDirection, VerifierStatus
from app.schemas.sector_brief import SectorBrief
from app.services.strategies.funnel_research.company.prompts import (
    build_company_messages,
)
from app.services.strategies.funnel_research.company.selector import CompanyIdea


def _sector_brief(sector_entity_id: uuid.UUID) -> SectorBrief:
    return SectorBrief(
        sector_entity_id=sector_entity_id,
        sector_name="Information Technology",
        direction=SectorCallDirection.overweight,
        themes=[],
        companies=[],
        watch_items=[],
        cited_claims=[],
        confidence=0.7,
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


def _company_idea(sector_entity_id: uuid.UUID) -> CompanyIdea:
    return CompanyIdea(
        company_name="Apple Inc.",
        ticker="AAPL",
        direction=SectorCallDirection.overweight,
        conviction=0.85,
        sector_entity_id=sector_entity_id,
        sector_name="Information Technology",
        evidence_ids=(),
        sector_company_index=0,
    )


def _chunks() -> list[EvidenceChunkRef]:
    return [
        EvidenceChunkRef(
            chunk_id=uuid.uuid4(),
            evidence_id=uuid.uuid4(),
            chunk_index=0,
            text="Apple revenue grew 12% YoY",
            attributes={"source": "tiingo_news"},
        ),
        EvidenceChunkRef(
            chunk_id=uuid.uuid4(),
            evidence_id=uuid.uuid4(),
            chunk_index=0,
            text="AAPL close=192.0 volume=10m",
            attributes={"source": "polygon_aggregates"},
        ),
    ]


def test_messages_include_company_name_and_critical_block() -> None:
    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    messages = build_company_messages(
        company_idea=_company_idea(sector_entity_id),
        company_entity_id=company_entity_id,
        sector_brief=_sector_brief(sector_entity_id),
        digest_markdown="# Sector digest\n- AAPL up",
        chunks=_chunks(),
        evidence_ids=[uuid.uuid4()],
    )
    assert messages[0].role == "system"
    assert messages[1].role == "user"
    user_text = messages[1].content
    assert "Apple Inc." in user_text
    assert user_text.count("CRITICAL:") >= 2
    assert "Output schema (strict)" in user_text


def test_messages_include_chunks_and_sector_context() -> None:
    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    chunks = _chunks()
    messages = build_company_messages(
        company_idea=_company_idea(sector_entity_id),
        company_entity_id=company_entity_id,
        sector_brief=_sector_brief(sector_entity_id),
        digest_markdown="",
        chunks=chunks,
        evidence_ids=[],
    )
    user_text = messages[1].content
    assert "Information Technology" in user_text
    assert "Apple revenue grew 12% YoY" in user_text
    assert "AAPL close=192.0 volume=10m" in user_text
    assert "tiingo_news" in user_text


def test_messages_include_company_entity_id_and_sector_entity_id() -> None:
    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    messages = build_company_messages(
        company_idea=_company_idea(sector_entity_id),
        company_entity_id=company_entity_id,
        sector_brief=_sector_brief(sector_entity_id),
        digest_markdown="",
        chunks=[],
        evidence_ids=[],
    )
    user_text = messages[1].content
    assert str(company_entity_id) in user_text
    assert str(sector_entity_id) in user_text


def test_messages_include_regeneration_feedback_when_provided() -> None:
    sector_entity_id = uuid.uuid4()
    messages = build_company_messages(
        company_idea=_company_idea(sector_entity_id),
        company_entity_id=uuid.uuid4(),
        sector_brief=_sector_brief(sector_entity_id),
        digest_markdown="",
        chunks=[],
        evidence_ids=[],
        regeneration_feedback=["quote not found in chunk"],
    )
    user_text = messages[1].content
    assert "Previous attempt rejected because" in user_text
    assert "quote not found in chunk" in user_text


def test_messages_chunks_sorted_for_determinism() -> None:
    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    chunks = _chunks()
    a = build_company_messages(
        company_idea=_company_idea(sector_entity_id),
        company_entity_id=company_entity_id,
        sector_brief=_sector_brief(sector_entity_id),
        digest_markdown="",
        chunks=chunks,
        evidence_ids=[],
    )
    b = build_company_messages(
        company_idea=_company_idea(sector_entity_id),
        company_entity_id=company_entity_id,
        sector_brief=_sector_brief(sector_entity_id),
        digest_markdown="",
        chunks=list(reversed(chunks)),
        evidence_ids=[],
    )
    assert a[1].content == b[1].content
