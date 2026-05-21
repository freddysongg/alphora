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
from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import (
    CitedClaim,
    SectorCall,
    SectorCallDirection,
    VerifierStatus,
)
from app.schemas.sector_brief import SectorBrief
from app.services.strategies.funnel_research.sector.verifier import (
    run_sector_regen_loop,
    verify_sector_once,
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


def _sector_call() -> SectorCall:
    return SectorCall(
        sector_entity_id=uuid.UUID(int=100),
        sector_name="Information Technology",
        direction=SectorCallDirection.overweight,
        conviction=0.8,
        evidence_ids=[],
    )


def _chunk(text: str = "AAPL grew 12% in Q1") -> EvidenceChunkRef:
    return EvidenceChunkRef(
        chunk_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        chunk_index=0,
        text=text,
        attributes={"source": "tiingo_news"},
    )


def _brief_with(
    *,
    sector_call: SectorCall,
    cited_claims: list[CitedClaim],
) -> SectorBrief:
    return SectorBrief(
        sector_entity_id=sector_call.sector_entity_id,
        sector_name=sector_call.sector_name,
        direction=sector_call.direction,
        themes=[],
        companies=[],
        watch_items=[],
        cited_claims=cited_claims,
        confidence=0.7,
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


def test_verify_once_passes_for_matching_brief() -> None:
    call = _sector_call()
    chunk = _chunk()
    claim = CitedClaim(
        claim_text="apple grew",
        exact_quote="AAPL grew 12% in Q1",
        chunk_id=chunk.chunk_id,
        source="tiingo_news",
    )
    brief = _brief_with(sector_call=call, cited_claims=[claim])
    result = verify_sector_once(brief=brief, chunks=[chunk], sector_call=call)
    assert result.is_valid
    assert result.reasons == []


def test_verify_once_rejects_sector_name_mismatch() -> None:
    call = _sector_call()
    brief = SectorBrief(
        sector_entity_id=call.sector_entity_id,
        sector_name="Energy",
        direction=call.direction,
        themes=[],
        companies=[],
        watch_items=[],
        cited_claims=[],
        confidence=0.5,
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )
    result = verify_sector_once(brief=brief, chunks=[], sector_call=call)
    assert not result.is_valid
    assert any("sector_name mismatch" in r for r in result.reasons)


def test_verify_once_rejects_sector_entity_id_mismatch() -> None:
    call = _sector_call()
    brief = SectorBrief(
        sector_entity_id=uuid.UUID(int=999),
        sector_name=call.sector_name,
        direction=call.direction,
        themes=[],
        companies=[],
        watch_items=[],
        cited_claims=[],
        confidence=0.5,
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )
    result = verify_sector_once(brief=brief, chunks=[], sector_call=call)
    assert not result.is_valid
    assert any("sector_entity_id mismatch" in r for r in result.reasons)


def test_verify_once_rejects_missing_quote() -> None:
    call = _sector_call()
    chunk = _chunk("AAPL grew 12% in Q1")
    claim = CitedClaim(
        claim_text="fabricated",
        exact_quote="not in chunk",
        chunk_id=chunk.chunk_id,
        source="tiingo_news",
    )
    brief = _brief_with(sector_call=call, cited_claims=[claim])
    result = verify_sector_once(brief=brief, chunks=[chunk], sector_call=call)
    assert not result.is_valid
    assert any("quote not in chunk" in r for r in result.reasons)


def test_verify_once_rejects_unknown_chunk_id() -> None:
    call = _sector_call()
    chunk = _chunk()
    claim = CitedClaim(
        claim_text="x",
        exact_quote="x",
        chunk_id=uuid.uuid4(),
        source="tiingo_news",
    )
    brief = _brief_with(sector_call=call, cited_claims=[claim])
    result = verify_sector_once(brief=brief, chunks=[chunk], sector_call=call)
    assert not result.is_valid
    assert any("chunk_id not in corpus" in r for r in result.reasons)


@pytest.mark.asyncio
async def test_regen_loop_returns_verified_on_first_pass(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    call = _sector_call()
    chunk = _chunk()
    claim = CitedClaim(
        claim_text="apple grew",
        exact_quote="AAPL grew 12% in Q1",
        chunk_id=chunk.chunk_id,
        source="tiingo_news",
    )
    brief = _brief_with(sector_call=call, cited_claims=[claim])

    regen_called: dict[str, int] = {"n": 0}

    async def regen(_reasons: list[str]) -> SectorBrief:
        regen_called["n"] += 1
        raise AssertionError("should not regen")

    result = await run_sector_regen_loop(
        session=db_session,
        run_id=run_id,
        initial_brief=brief,
        chunks=[chunk],
        sector_call=call,
        regenerate=regen,
    )
    assert result.brief.verifier_status is VerifierStatus.verified
    assert result.regeneration_count == 0
    assert regen_called["n"] == 0


@pytest.mark.asyncio
async def test_regen_loop_persists_unverified_after_cap(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    call = _sector_call()
    chunk = _chunk()
    bad_claim = CitedClaim(
        claim_text="x",
        exact_quote="not present in chunk",
        chunk_id=chunk.chunk_id,
        source="tiingo_news",
    )
    brief = _brief_with(sector_call=call, cited_claims=[bad_claim])

    async def regen_with_same_bad_quote(_reasons: list[str]) -> SectorBrief:
        return _brief_with(sector_call=call, cited_claims=[bad_claim])

    result = await run_sector_regen_loop(
        session=db_session,
        run_id=run_id,
        initial_brief=brief,
        chunks=[chunk],
        sector_call=call,
        regenerate=regen_with_same_bad_quote,
    )
    assert result.brief.verifier_status is VerifierStatus.quote_unverified
    assert result.regeneration_count >= 2
    events = (await db_session.execute(select(RunEvent))).scalars().all()
    assert any(
        isinstance(event.data, dict)
        and event.data.get("event") == "sector_verifier_regeneration"
        for event in events
    )


@pytest.mark.asyncio
async def test_regen_loop_recovers_on_second_attempt(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    call = _sector_call()
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
    initial = _brief_with(sector_call=call, cited_claims=[bad_claim])
    fixed = _brief_with(sector_call=call, cited_claims=[good_claim])

    async def regen(_reasons: list[str]) -> SectorBrief:
        return fixed

    result = await run_sector_regen_loop(
        session=db_session,
        run_id=run_id,
        initial_brief=initial,
        chunks=[chunk],
        sector_call=call,
        regenerate=regen,
    )
    assert result.brief.verifier_status is VerifierStatus.verified
    assert result.regeneration_count == 1
