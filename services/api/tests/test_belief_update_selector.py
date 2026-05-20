"""Tests for belief_update.selector: hypothesis filter + chunk walk +
idempotency + cap."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_company import CompanyThesis as CompanyThesisRow
from app.db.models_graph import (
    Entity,
    EntityType,
    Evidence,
    EvidenceChunk,
    Hypothesis,
    Relation,
    RelationType,
)
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_runs import (
    ResearchRun,
    RunStatus,
    Strategy,
)
from app.db.models_sector import SectorBrief as SectorBriefRow
from app.services.belief_update.selector import select_belief_update_inputs


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 20),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.commit()
    return run.id


async def _seed_entity(
    session: AsyncSession, *, kind: EntityType, name: str
) -> uuid.UUID:
    entity = Entity(
        type=kind.value,
        canonical_name=name,
        aliases=[],
        external_ids={},
        attributes={},
    )
    session.add(entity)
    await session.flush()
    return entity.id


async def _seed_hypothesis(
    session: AsyncSession,
    *,
    claim: str,
    scope_entity_ids: list[uuid.UUID],
    status: str = "active",
) -> Hypothesis:
    entity = Entity(
        type=EntityType.hypothesis.value,
        canonical_name=claim,
        aliases=[claim],
        external_ids={},
        attributes={},
    )
    session.add(entity)
    await session.flush()
    hypothesis = Hypothesis(
        claim_text=claim,
        scope_entity_ids=[str(eid) for eid in scope_entity_ids],
        scope_theme_ids=[],
        status=status,
        belief=0.5,
        belief_history=[],
        entity_id=entity.id,
    )
    session.add(hypothesis)
    await session.flush()
    return hypothesis


async def _seed_evidence_with_chunks(
    session: AsyncSession, *, source: str, chunk_count: int
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    evidence = Evidence(
        source=source,
        document_id=f"{source}|doc|{uuid.uuid4()}",
        raw_url=None,
        content_hash=uuid.uuid4().hex,
        structured={},
    )
    session.add(evidence)
    await session.flush()
    chunk_ids: list[uuid.UUID] = []
    for idx in range(chunk_count):
        chunk = EvidenceChunk(
            evidence_id=evidence.id,
            chunk_index=idx,
            text=f"chunk {idx} from {source}",
            start_offset=None,
            end_offset=None,
            attributes={"source": source},
            content_hash=uuid.uuid4().hex,
        )
        session.add(chunk)
        await session.flush()
        chunk_ids.append(chunk.id)
    return evidence.id, chunk_ids


@pytest.mark.asyncio
async def test_select_returns_empty_when_run_has_no_briefs(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    result = await select_belief_update_inputs(
        session=db_session, run_id=run_id, max_chunks_per_hypothesis=50
    )
    assert result == []


@pytest.mark.asyncio
async def test_select_pulls_chunks_from_sector_brief_evidence_ids(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_entity_id = await _seed_entity(
        db_session, kind=EntityType.sector, name="Information Technology"
    )
    evidence_id, chunk_ids = await _seed_evidence_with_chunks(
        db_session, source="tiingo_news", chunk_count=3
    )
    db_session.add(
        SectorBriefRow(
            run_id=run_id,
            sector_entity_id=sector_entity_id,
            direction="overweight",
            payload={"evidence_ids": [str(evidence_id)]},
            verifier_status="verified",
            regeneration_count=0,
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
            wall_clock_ms=0,
        )
    )
    await db_session.commit()
    hypothesis = await _seed_hypothesis(
        db_session,
        claim="Tech earnings will beat",
        scope_entity_ids=[sector_entity_id],
    )
    await db_session.commit()

    result = await select_belief_update_inputs(
        session=db_session, run_id=run_id, max_chunks_per_hypothesis=50
    )

    assert len(result) == 1
    candidate = result[0]
    assert candidate.hypothesis.id == hypothesis.id
    assert {chunk.id for chunk in candidate.chunks} == set(chunk_ids)


@pytest.mark.asyncio
async def test_select_pulls_chunks_from_company_thesis_evidence_ids(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    company_entity_id = await _seed_entity(
        db_session, kind=EntityType.company, name="Apple Inc."
    )
    sector_entity_id = await _seed_entity(
        db_session, kind=EntityType.sector, name="Information Technology"
    )
    evidence_id, chunk_ids = await _seed_evidence_with_chunks(
        db_session, source="polygon_aggregates", chunk_count=2
    )
    db_session.add(
        CompanyThesisRow(
            run_id=run_id,
            company_entity_id=company_entity_id,
            sector_entity_id=sector_entity_id,
            ticker="AAPL",
            direction="overweight",
            payload={"evidence_ids": [str(evidence_id)]},
            verifier_status="verified",
            regeneration_count=0,
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
            wall_clock_ms=0,
        )
    )
    await db_session.commit()
    hypothesis = await _seed_hypothesis(
        db_session,
        claim="Apple maintains gross margin",
        scope_entity_ids=[company_entity_id],
    )
    await db_session.commit()

    result = await select_belief_update_inputs(
        session=db_session, run_id=run_id, max_chunks_per_hypothesis=50
    )

    assert len(result) == 1
    assert result[0].hypothesis.id == hypothesis.id
    assert {chunk.id for chunk in result[0].chunks} == set(chunk_ids)


@pytest.mark.asyncio
async def test_select_macro_scope_pulls_macro_brief_evidence(
    db_session: AsyncSession,
) -> None:
    """Hypothesis scoped to a theme entity pulls chunks via MacroBrief.evidence_ids.

    EntityType.macro_indicator does not exist in the enum; EntityType.theme is
    used instead. The selector treats any scope entity that isn't sector/company
    as macro-scope and resolves evidence from the run's MacroBrief.evidence_ids.
    """
    run_id = await _seed_run(db_session)
    theme_entity_id = await _seed_entity(
        db_session, kind=EntityType.theme, name="Federal Reserve policy"
    )
    evidence_id, chunk_ids = await _seed_evidence_with_chunks(
        db_session, source="fred", chunk_count=4
    )
    db_session.add(
        MacroBriefRow(
            run_id=run_id,
            themes=[],
            sector_calls=[],
            watch_items=[],
            cited_claims=[],
            proposed_hypotheses=[],
            confidence=0.5,
            verifier_status="verified",
            regeneration_count=0,
            evidence_ids=[str(evidence_id)],
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
        )
    )
    await db_session.commit()
    await _seed_hypothesis(
        db_session,
        claim="Rates stay above 4%",
        scope_entity_ids=[theme_entity_id],
    )
    await db_session.commit()

    result = await select_belief_update_inputs(
        session=db_session, run_id=run_id, max_chunks_per_hypothesis=50
    )

    assert len(result) == 1
    assert {chunk.id for chunk in result[0].chunks} == set(chunk_ids)


@pytest.mark.asyncio
async def test_select_filters_chunks_with_existing_belief_relation(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_entity_id = await _seed_entity(
        db_session, kind=EntityType.sector, name="Energy"
    )
    evidence_id, chunk_ids = await _seed_evidence_with_chunks(
        db_session, source="fred", chunk_count=3
    )
    db_session.add(
        SectorBriefRow(
            run_id=run_id,
            sector_entity_id=sector_entity_id,
            direction="underweight",
            payload={"evidence_ids": [str(evidence_id)]},
            verifier_status="verified",
            regeneration_count=0,
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
            wall_clock_ms=0,
        )
    )
    await db_session.commit()
    hypothesis = await _seed_hypothesis(
        db_session,
        claim="Energy demand softens",
        scope_entity_ids=[sector_entity_id],
    )
    db_session.add(
        Relation(
            from_id=sector_entity_id,
            to_id=hypothesis.entity_id,
            type=RelationType.supports_hypothesis.value,
            chunk_id=chunk_ids[0],
            sign=1.0,
            is_explicit=True,
        )
    )
    await db_session.commit()

    result = await select_belief_update_inputs(
        session=db_session, run_id=run_id, max_chunks_per_hypothesis=50
    )

    assert len(result) == 1
    surviving_ids = {chunk.id for chunk in result[0].chunks}
    assert chunk_ids[0] not in surviving_ids
    assert surviving_ids == {chunk_ids[1], chunk_ids[2]}


@pytest.mark.asyncio
async def test_select_caps_chunks_at_limit_keeping_newest(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_entity_id = await _seed_entity(
        db_session, kind=EntityType.sector, name="Health Care"
    )
    evidence_id, chunk_ids = await _seed_evidence_with_chunks(
        db_session, source="tiingo_news", chunk_count=5
    )
    db_session.add(
        SectorBriefRow(
            run_id=run_id,
            sector_entity_id=sector_entity_id,
            direction="overweight",
            payload={"evidence_ids": [str(evidence_id)]},
            verifier_status="verified",
            regeneration_count=0,
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
            wall_clock_ms=0,
        )
    )
    await db_session.commit()
    await _seed_hypothesis(
        db_session,
        claim="HC margins improve",
        scope_entity_ids=[sector_entity_id],
    )
    await db_session.commit()

    result = await select_belief_update_inputs(
        session=db_session, run_id=run_id, max_chunks_per_hypothesis=2
    )

    assert len(result) == 1
    assert {chunk.id for chunk in result[0].chunks} == {chunk_ids[-2], chunk_ids[-1]}


@pytest.mark.asyncio
async def test_select_excludes_hypothesis_whose_scope_does_not_overlap(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    in_scope = await _seed_entity(
        db_session, kind=EntityType.sector, name="Financials"
    )
    out_of_scope = await _seed_entity(
        db_session, kind=EntityType.sector, name="Real Estate"
    )
    evidence_id, _ = await _seed_evidence_with_chunks(
        db_session, source="fred", chunk_count=1
    )
    db_session.add(
        SectorBriefRow(
            run_id=run_id,
            sector_entity_id=in_scope,
            direction="overweight",
            payload={"evidence_ids": [str(evidence_id)]},
            verifier_status="verified",
            regeneration_count=0,
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
            wall_clock_ms=0,
        )
    )
    await db_session.commit()
    await _seed_hypothesis(
        db_session,
        claim="REIT cap rates compress",
        scope_entity_ids=[out_of_scope],
    )
    await db_session.commit()

    result = await select_belief_update_inputs(
        session=db_session, run_id=run_id, max_chunks_per_hypothesis=50
    )

    assert result == []


@pytest.mark.asyncio
async def test_select_excludes_archived_and_terminal_hypotheses(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_entity_id = await _seed_entity(
        db_session, kind=EntityType.sector, name="Industrials"
    )
    evidence_id, _ = await _seed_evidence_with_chunks(
        db_session, source="fred", chunk_count=2
    )
    db_session.add(
        SectorBriefRow(
            run_id=run_id,
            sector_entity_id=sector_entity_id,
            direction="neutral",
            payload={"evidence_ids": [str(evidence_id)]},
            verifier_status="verified",
            regeneration_count=0,
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
            wall_clock_ms=0,
        )
    )
    await db_session.commit()
    await _seed_hypothesis(
        db_session,
        claim="Industrial output expands",
        scope_entity_ids=[sector_entity_id],
        status="validated",
    )
    archived = await _seed_hypothesis(
        db_session,
        claim="Industrial CapEx pulls back",
        scope_entity_ids=[sector_entity_id],
        status="active",
    )
    archived.archived_at = datetime.now(UTC)
    await db_session.commit()

    result = await select_belief_update_inputs(
        session=db_session, run_id=run_id, max_chunks_per_hypothesis=50
    )

    assert result == []
