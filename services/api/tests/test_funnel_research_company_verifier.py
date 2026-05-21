import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import (
    ResearchRun,
    RunEvent,
    RunStatus,
    Strategy,
)
from app.schemas.company_thesis import CompanyThesis
from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import (
    CitedClaim,
    SectorCallDirection,
    VerifierStatus,
)
from app.services.strategies.funnel_research.company.selector import CompanyIdea
from app.services.strategies.funnel_research.company.verifier import (
    run_company_regen_loop,
    verify_company_once,
)


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 19),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.commit()
    return run.id


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


def _chunk(text: str = "AAPL grew 12% in Q1") -> EvidenceChunkRef:
    return EvidenceChunkRef(
        chunk_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        chunk_index=0,
        text=text,
        attributes={"source": "tiingo_news"},
    )


def _thesis(
    *,
    company_idea: CompanyIdea,
    company_entity_id: uuid.UUID,
    cited_claims: list[CitedClaim],
    company_name: str | None = None,
    sector_entity_id: uuid.UUID | None = None,
) -> CompanyThesis:
    return CompanyThesis(
        company_entity_id=company_entity_id,
        company_name=company_name or company_idea.company_name,
        sector_entity_id=sector_entity_id or company_idea.sector_entity_id,
        sector_name=company_idea.sector_name,
        ticker=company_idea.ticker,
        direction=company_idea.direction,
        conviction=company_idea.conviction,
        bull_case="Strong fundamentals",
        bear_case="Demand risks",
        catalysts=[],
        risks=[],
        cited_claims=cited_claims,
        confidence=0.7,
        evidence_ids=[],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


def test_verify_once_passes_for_matching_thesis() -> None:
    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    idea = _company_idea(sector_entity_id)
    chunk = _chunk()
    claim = CitedClaim(
        claim_text="apple grew",
        exact_quote="AAPL grew 12% in Q1",
        chunk_id=chunk.chunk_id,
        source="tiingo_news",
    )
    thesis = _thesis(
        company_idea=idea,
        company_entity_id=company_entity_id,
        cited_claims=[claim],
    )
    result = verify_company_once(
        thesis=thesis,
        chunks=[chunk],
        company_idea=idea,
        company_entity_id=company_entity_id,
    )
    assert result.is_valid
    assert result.reasons == []


def test_verify_once_rejects_company_name_mismatch() -> None:
    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    idea = _company_idea(sector_entity_id)
    thesis = _thesis(
        company_idea=idea,
        company_entity_id=company_entity_id,
        cited_claims=[],
        company_name="Microsoft Corp",
    )
    result = verify_company_once(
        thesis=thesis,
        chunks=[],
        company_idea=idea,
        company_entity_id=company_entity_id,
    )
    assert not result.is_valid
    assert any("company_name mismatch" in r for r in result.reasons)


def test_verify_once_rejects_company_entity_id_mismatch() -> None:
    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    idea = _company_idea(sector_entity_id)
    thesis = _thesis(
        company_idea=idea,
        company_entity_id=uuid.uuid4(),
        cited_claims=[],
    )
    result = verify_company_once(
        thesis=thesis,
        chunks=[],
        company_idea=idea,
        company_entity_id=company_entity_id,
    )
    assert not result.is_valid
    assert any("company_entity_id mismatch" in r for r in result.reasons)


def test_verify_once_rejects_sector_entity_id_mismatch() -> None:
    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    idea = _company_idea(sector_entity_id)
    thesis = _thesis(
        company_idea=idea,
        company_entity_id=company_entity_id,
        cited_claims=[],
        sector_entity_id=uuid.uuid4(),
    )
    result = verify_company_once(
        thesis=thesis,
        chunks=[],
        company_idea=idea,
        company_entity_id=company_entity_id,
    )
    assert not result.is_valid
    assert any("sector_entity_id mismatch" in r for r in result.reasons)


def test_verify_once_rejects_missing_quote() -> None:
    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    idea = _company_idea(sector_entity_id)
    chunk = _chunk()
    claim = CitedClaim(
        claim_text="fabricated",
        exact_quote="not in chunk",
        chunk_id=chunk.chunk_id,
        source="tiingo_news",
    )
    thesis = _thesis(
        company_idea=idea,
        company_entity_id=company_entity_id,
        cited_claims=[claim],
    )
    result = verify_company_once(
        thesis=thesis,
        chunks=[chunk],
        company_idea=idea,
        company_entity_id=company_entity_id,
    )
    assert not result.is_valid
    assert any("quote not in chunk" in r for r in result.reasons)


def test_verify_once_rejects_unknown_chunk_id() -> None:
    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    idea = _company_idea(sector_entity_id)
    chunk = _chunk()
    claim = CitedClaim(
        claim_text="x",
        exact_quote="x",
        chunk_id=uuid.uuid4(),
        source="tiingo_news",
    )
    thesis = _thesis(
        company_idea=idea,
        company_entity_id=company_entity_id,
        cited_claims=[claim],
    )
    result = verify_company_once(
        thesis=thesis,
        chunks=[chunk],
        company_idea=idea,
        company_entity_id=company_entity_id,
    )
    assert not result.is_valid
    assert any("chunk_id not in corpus" in r for r in result.reasons)


@pytest.mark.asyncio
async def test_regen_loop_returns_verified_on_first_pass(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    idea = _company_idea(sector_entity_id)
    chunk = _chunk()
    claim = CitedClaim(
        claim_text="apple grew",
        exact_quote="AAPL grew 12% in Q1",
        chunk_id=chunk.chunk_id,
        source="tiingo_news",
    )
    thesis = _thesis(
        company_idea=idea,
        company_entity_id=company_entity_id,
        cited_claims=[claim],
    )

    regen_called: dict[str, int] = {"n": 0}

    async def regen(_reasons: list[str]) -> CompanyThesis:
        regen_called["n"] += 1
        raise AssertionError("should not regen")

    result = await run_company_regen_loop(
        session=db_session,
        run_id=run_id,
        initial_thesis=thesis,
        chunks=[chunk],
        company_idea=idea,
        company_entity_id=company_entity_id,
        regenerate=regen,
    )
    assert result.thesis.verifier_status is VerifierStatus.verified
    assert result.regeneration_count == 0
    assert regen_called["n"] == 0


@pytest.mark.asyncio
async def test_regen_loop_persists_unverified_after_cap(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    idea = _company_idea(sector_entity_id)
    chunk = _chunk()
    bad_claim = CitedClaim(
        claim_text="x",
        exact_quote="not present in chunk",
        chunk_id=chunk.chunk_id,
        source="tiingo_news",
    )
    thesis = _thesis(
        company_idea=idea,
        company_entity_id=company_entity_id,
        cited_claims=[bad_claim],
    )

    async def regen_with_same_bad_quote(_reasons: list[str]) -> CompanyThesis:
        return _thesis(
            company_idea=idea,
            company_entity_id=company_entity_id,
            cited_claims=[bad_claim],
        )

    result = await run_company_regen_loop(
        session=db_session,
        run_id=run_id,
        initial_thesis=thesis,
        chunks=[chunk],
        company_idea=idea,
        company_entity_id=company_entity_id,
        regenerate=regen_with_same_bad_quote,
    )
    assert result.thesis.verifier_status is VerifierStatus.quote_unverified
    assert result.regeneration_count >= 2
    events = (await db_session.execute(select(RunEvent))).scalars().all()
    assert any(
        isinstance(event.data, dict)
        and event.data.get("event") == "company_verifier_regeneration"
        for event in events
    )


@pytest.mark.asyncio
async def test_regen_loop_recovers_on_second_attempt(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    idea = _company_idea(sector_entity_id)
    chunk = _chunk()
    bad_claim = CitedClaim(
        claim_text="x",
        exact_quote="not present",
        chunk_id=chunk.chunk_id,
        source="tiingo_news",
    )
    good_claim = CitedClaim(
        claim_text="apple grew",
        exact_quote="AAPL grew 12% in Q1",
        chunk_id=chunk.chunk_id,
        source="tiingo_news",
    )
    initial = _thesis(
        company_idea=idea,
        company_entity_id=company_entity_id,
        cited_claims=[bad_claim],
    )
    fixed = _thesis(
        company_idea=idea,
        company_entity_id=company_entity_id,
        cited_claims=[good_claim],
    )

    async def regen(_reasons: list[str]) -> CompanyThesis:
        return fixed

    result = await run_company_regen_loop(
        session=db_session,
        run_id=run_id,
        initial_thesis=initial,
        chunks=[chunk],
        company_idea=idea,
        company_entity_id=company_entity_id,
        regenerate=regen,
    )
    assert result.thesis.verifier_status is VerifierStatus.verified
    assert result.regeneration_count == 1
