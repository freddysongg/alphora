import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import (
    Entity,
    EntityType,
    Evidence,
    EvidenceChunk,
    Relation,
)
from app.db.models_runs import (
    ResearchRun,
    RunEvent,
    RunEventLevel,
    RunStatus,
    Strategy,
)
from app.schemas.common import EntityTypeEnum, RelationTypeEnum
from app.schemas.extraction import (
    CandidateEntity,
    CandidateRelation,
    ExtractionResult,
)
from app.services.strategies.funnel_research.company.graph import (
    persist_company_candidates,
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


async def _seed_entity(session: AsyncSession, canonical_name: str) -> uuid.UUID:
    entity = Entity(
        type=EntityType.company.value,
        canonical_name=canonical_name,
        aliases=[canonical_name],
        external_ids={},
        attributes={},
    )
    session.add(entity)
    await session.commit()
    return entity.id


def _entity_candidate(span: str) -> CandidateEntity:
    return CandidateEntity(
        text_span=span,
        suggested_type=EntityTypeEnum.company,
        context_excerpt=f"{span} reported strong revenue.",
        exact_quote=f"{span} reported strong revenue.",
        chunk_id=uuid.uuid4(),
        extraction_confidence=0.9,
    )


def _relation_candidate(
    subj: str, obj: str, predicate: RelationTypeEnum = RelationTypeEnum.competes_with
) -> CandidateRelation:
    return CandidateRelation(
        subj_span=subj,
        predicate=predicate,
        obj_span=obj,
        exact_quote=f"{subj} competes with {obj}.",
        chunk_id=uuid.uuid4(),
        is_explicit=True,
        extraction_confidence=0.8,
    )


def _extraction_result(
    *,
    entities: list[CandidateEntity],
    relations: list[CandidateRelation],
) -> ExtractionResult:
    chunk_id = entities[0].chunk_id if entities else uuid.uuid4()
    return ExtractionResult(
        chunk_id=chunk_id,
        candidate_entities=entities,
        candidate_relations=relations,
        model_id="gpt-4o-mini",
        prompt_version="extract-v1",
        verified=True,
        rejection_reasons=[],
    )


@pytest.mark.asyncio
async def test_persist_company_resolves_candidates_and_writes_relation(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    await _seed_entity(db_session, "Apple Inc.")
    await _seed_entity(db_session, "Microsoft Corp")

    apple = _entity_candidate("Apple Inc.")
    msft = _entity_candidate("Microsoft Corp")
    relation = _relation_candidate("Apple Inc.", "Microsoft Corp")
    result = _extraction_result(entities=[apple, msft], relations=[relation])

    outcome = await persist_company_candidates(
        session=db_session,
        run_id=run_id,
        extraction_results=[result],
    )

    assert outcome.resolved_entity_count == 2
    assert outcome.persisted_relation_count == 1
    assert outcome.skipped_relation_count == 0
    relations = (await db_session.execute(select(Relation))).scalars().all()
    assert len(relations) == 1
    assert relations[0].prompt_version == "extract-v1"


@pytest.mark.asyncio
async def test_persist_company_skips_relation_with_unresolved_endpoint(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    await _seed_entity(db_session, "Apple Inc.")

    apple = _entity_candidate("Apple Inc.")
    relation = _relation_candidate("Apple Inc.", "Ghost Corp")
    result = _extraction_result(entities=[apple], relations=[relation])

    outcome = await persist_company_candidates(
        session=db_session,
        run_id=run_id,
        extraction_results=[result],
    )

    assert outcome.resolved_entity_count >= 1
    assert outcome.persisted_relation_count == 0
    assert outcome.skipped_relation_count == 1
    relations = (await db_session.execute(select(Relation))).scalars().all()
    assert len(relations) == 0
    warn_events = (
        await db_session.execute(
            select(RunEvent).where(RunEvent.level == RunEventLevel.warn)
        )
    ).scalars().all()
    assert any(
        isinstance(event.data, dict)
        and event.data.get("event") == "company_relation_skipped"
        for event in warn_events
    )


@pytest.mark.asyncio
async def test_persist_company_handles_empty_extraction_results(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    outcome = await persist_company_candidates(
        session=db_session,
        run_id=run_id,
        extraction_results=[],
    )
    assert outcome.resolved_entity_count == 0
    assert outcome.persisted_relation_count == 0
    assert outcome.skipped_relation_count == 0


@pytest.mark.asyncio
async def test_persist_company_skips_self_loop_relations(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    await _seed_entity(db_session, "Apple Inc.")

    apple = _entity_candidate("Apple Inc.")
    self_loop = _relation_candidate("Apple Inc.", "Apple Inc.")
    result = _extraction_result(entities=[apple], relations=[self_loop])

    outcome = await persist_company_candidates(
        session=db_session,
        run_id=run_id,
        extraction_results=[result],
    )

    assert outcome.persisted_relation_count == 0
    assert outcome.skipped_relation_count == 1


async def _seed_chunk(
    session: AsyncSession, *, chunk_id: uuid.UUID
) -> Evidence:
    evidence = Evidence(
        source="news",
        document_id=str(uuid.uuid4()),
        content_hash=uuid.uuid4().hex,
    )
    session.add(evidence)
    await session.flush()
    chunk = EvidenceChunk(
        id=chunk_id,
        evidence_id=evidence.id,
        chunk_index=0,
        text="seeded chunk text",
        content_hash=uuid.uuid4().hex,
    )
    session.add(chunk)
    await session.flush()
    return evidence


@pytest.mark.asyncio
async def test_persist_company_populates_relation_provenance(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    await _seed_entity(db_session, "Apple Inc.")
    await _seed_entity(db_session, "Microsoft Corp")

    chunk_id = uuid.uuid4()
    evidence = await _seed_chunk(db_session, chunk_id=chunk_id)

    apple = _entity_candidate("Apple Inc.")
    msft = _entity_candidate("Microsoft Corp")
    relation = CandidateRelation(
        subj_span="Apple Inc.",
        predicate=RelationTypeEnum.competes_with,
        obj_span="Microsoft Corp",
        exact_quote="Apple competes with Microsoft.",
        chunk_id=chunk_id,
        is_explicit=True,
        extraction_confidence=0.75,
    )
    result = _extraction_result(entities=[apple, msft], relations=[relation])

    outcome = await persist_company_candidates(
        session=db_session,
        run_id=run_id,
        extraction_results=[result],
    )
    assert outcome.persisted_relation_count == 1
    persisted = (await db_session.execute(select(Relation))).scalar_one()
    assert persisted.source_id == evidence.id
    assert persisted.chunk_id == chunk_id
    assert persisted.extracted_by_model == "gpt-4o-mini"
    assert persisted.prompt_version == "extract-v1"
    assert persisted.quote == "Apple competes with Microsoft."
    assert persisted.is_explicit is True
    assert persisted.sign == 1.0
    assert persisted.relevance == 1.0
    assert persisted.extraction_confidence == 0.75
