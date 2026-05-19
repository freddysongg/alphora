import uuid

import pytest

from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import (
    CitedClaim,
    MacroBrief,
    ProposedHypothesis,
    SectorCall,
    SectorCallDirection,
    Theme,
    VerifierStatus,
    WatchItem,
)


def _brief(claim_quote: str, claim_chunk_id: uuid.UUID, sector_name: str, sector_eid: uuid.UUID) -> MacroBrief:
    return MacroBrief(
        themes=[Theme(name="rates", evidence_ids=[], confidence=0.5)],
        sector_calls=[
            SectorCall(
                sector_entity_id=sector_eid,
                sector_name=sector_name,
                direction=SectorCallDirection.overweight,
                conviction=0.6,
                evidence_ids=[],
            )
        ],
        watch_items=[WatchItem(name="watch", reason="r", evidence_ids=[])],
        cited_claims=[
            CitedClaim(
                claim_text="claim",
                exact_quote=claim_quote,
                chunk_id=claim_chunk_id,
                source="fred",
            )
        ],
        proposed_hypotheses=[ProposedHypothesis(claim_text="h", scope_entity_ids=[], evidence_ids=[])],
        confidence=0.5,
        evidence_ids=[],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


def _chunks(text: str) -> tuple[uuid.UUID, list[EvidenceChunkRef]]:
    chunk_id = uuid.uuid4()
    return chunk_id, [
        EvidenceChunkRef(
            chunk_id=chunk_id,
            evidence_id=uuid.uuid4(),
            chunk_index=0,
            text=text,
            attributes={"source": "fred"},
        )
    ]


@pytest.mark.asyncio
async def test_verifier_passes_when_quote_is_substring_of_chunk() -> None:
    from app.services.strategies.funnel_research._verifier import verify_once

    chunk_id, chunks = _chunks("Federal funds rate is 5.25 percent today.")
    energy_eid = uuid.uuid4()
    brief = _brief("Federal funds rate is 5.25 percent", chunk_id, "Energy", energy_eid)
    result = verify_once(
        brief=brief,
        chunks=chunks,
        sector_entity_ids={"Energy": energy_eid},
    )
    assert result.is_valid
    assert result.reasons == []


@pytest.mark.asyncio
async def test_verifier_whitespace_normalization_accepts_multiple_spaces() -> None:
    from app.services.strategies.funnel_research._verifier import verify_once

    chunk_id, chunks = _chunks("Federal     funds rate.")
    energy_eid = uuid.uuid4()
    brief = _brief("Federal funds rate.", chunk_id, "Energy", energy_eid)
    result = verify_once(
        brief=brief,
        chunks=chunks,
        sector_entity_ids={"Energy": energy_eid},
    )
    assert result.is_valid


@pytest.mark.asyncio
async def test_verifier_rejects_fabricated_quote() -> None:
    from app.services.strategies.funnel_research._verifier import verify_once

    chunk_id, chunks = _chunks("Real text.")
    energy_eid = uuid.uuid4()
    brief = _brief("fabricated text", chunk_id, "Energy", energy_eid)
    result = verify_once(
        brief=brief,
        chunks=chunks,
        sector_entity_ids={"Energy": energy_eid},
    )
    assert not result.is_valid
    assert any("quote not in chunk" in r for r in result.reasons)


@pytest.mark.asyncio
async def test_verifier_rejects_unknown_chunk_id() -> None:
    from app.services.strategies.funnel_research._verifier import verify_once

    _, chunks = _chunks("Real text.")
    energy_eid = uuid.uuid4()
    brief = _brief("Real text.", uuid.uuid4(), "Energy", energy_eid)
    result = verify_once(
        brief=brief,
        chunks=chunks,
        sector_entity_ids={"Energy": energy_eid},
    )
    assert not result.is_valid
    assert any("chunk_id not in corpus" in r for r in result.reasons)


@pytest.mark.asyncio
async def test_verifier_rejects_invalid_sector_name() -> None:
    from app.services.strategies.funnel_research._verifier import verify_once

    chunk_id, chunks = _chunks("Real text.")
    eid = uuid.uuid4()
    brief = _brief("Real text.", chunk_id, "Bogus Sector", eid)
    result = verify_once(
        brief=brief,
        chunks=chunks,
        sector_entity_ids={"Energy": eid},
    )
    assert not result.is_valid
    assert any("sector name not in allowlist" in r for r in result.reasons)


@pytest.mark.asyncio
async def test_verifier_rejects_mismatched_sector_entity_id() -> None:
    from app.services.strategies.funnel_research._verifier import verify_once

    chunk_id, chunks = _chunks("Real text.")
    correct = uuid.uuid4()
    wrong = uuid.uuid4()
    brief = _brief("Real text.", chunk_id, "Energy", wrong)
    result = verify_once(
        brief=brief,
        chunks=chunks,
        sector_entity_ids={"Energy": correct},
    )
    assert not result.is_valid
    assert any("sector_entity_id mismatch" in r for r in result.reasons)


@pytest.mark.asyncio
async def test_verifier_regen_loop_succeeds_on_second_attempt(
    db_session,
) -> None:
    from app.services.strategies.funnel_research._verifier import run_regen_loop

    chunk_id, chunks = _chunks("Real text.")
    energy_eid = uuid.uuid4()
    bad = _brief("fabricated", chunk_id, "Energy", energy_eid)
    good = _brief("Real text.", chunk_id, "Energy", energy_eid)
    run_id = uuid.uuid4()

    attempts: list[list[str]] = []

    async def regenerate(feedback: list[str]):
        attempts.append(feedback)
        return good

    result = await run_regen_loop(
        session=db_session,
        run_id=run_id,
        initial_brief=bad,
        chunks=chunks,
        sector_entity_ids={"Energy": energy_eid},
        regenerate=regenerate,
    )
    assert result.brief.verifier_status == VerifierStatus.verified
    assert result.regeneration_count == 1
    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_verifier_regen_loop_caps_at_two(db_session) -> None:
    from app.services.strategies.funnel_research._verifier import run_regen_loop

    chunk_id, chunks = _chunks("Real text.")
    energy_eid = uuid.uuid4()
    bad = _brief("fabricated", chunk_id, "Energy", energy_eid)
    run_id = uuid.uuid4()

    async def regenerate(feedback: list[str]):
        return bad

    result = await run_regen_loop(
        session=db_session,
        run_id=run_id,
        initial_brief=bad,
        chunks=chunks,
        sector_entity_ids={"Energy": energy_eid},
        regenerate=regenerate,
    )
    assert result.brief.verifier_status == VerifierStatus.quote_unverified
    assert result.regeneration_count == 2
    assert result.reasons
