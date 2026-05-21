"""Integration tests for the belief trigger pipeline."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import (
    BeliefRecomputation,
    DataSource,
    Entity,
    EntityType,
    Hypothesis,
    HypothesisStatus,
    Relation,
    RelationType,
)
from app.schemas.common import EntityTypeEnum
from app.schemas.extraction import CandidateEntity
from app.services.belief import (
    BELIEF_COMPUTATION_METHOD,
    ensure_hypothesis_entity,
    recompute_belief_for_hypothesis,
    recompute_beliefs_for_relations,
)
from app.services.entity_resolution import resolve_candidate


async def _seed_hypothesis(
    session: AsyncSession, *, claim_text: str = "thesis"
) -> Hypothesis:
    row = Hypothesis(
        claim_text=claim_text,
        scope_entity_ids=[],
        scope_theme_ids=[],
        status=HypothesisStatus.proposed.value,
        belief=None,
        belief_history=[],
    )
    session.add(row)
    await session.flush()
    return row


async def _seed_entity(session: AsyncSession, *, name: str) -> Entity:
    entity = Entity(
        type=EntityType.company.value,
        canonical_name=name,
        aliases=[name],
        external_ids={},
        attributes={},
    )
    session.add(entity)
    await session.flush()
    return entity


async def _write_belief_relation(
    session: AsyncSession,
    *,
    from_entity_id: uuid.UUID,
    hypothesis_entity_id: uuid.UUID,
    relation_type: RelationType,
    sign: float,
    confidence: float = 0.9,
    reliability_score: float | None = None,
    relevance: float | None = 1.0,
    created_at: datetime | None = None,
) -> Relation:
    data_source_id: uuid.UUID | None = None
    if reliability_score is not None:
        source = DataSource(
            name=f"src-{uuid.uuid4()}",
            kind="news",
            reliability_score=reliability_score,
        )
        session.add(source)
        await session.flush()
        data_source_id = source.id

    from app.db.models_graph import Evidence

    evidence = Evidence(
        source="news",
        source_id=data_source_id,
        document_id=str(uuid.uuid4()),
        content_hash=uuid.uuid4().hex,
    )
    session.add(evidence)
    await session.flush()

    relation = Relation(
        from_id=from_entity_id,
        to_id=hypothesis_entity_id,
        type=relation_type.value,
        attributes={},
        source_id=evidence.id,
        chunk_id=None,
        quote="evidence quote",
        relevance=relevance,
        extraction_confidence=confidence,
        prompt_version="belief-test-v1",
        extracted_by_model="gpt-4o-mini",
        is_explicit=True,
        sign=sign,
    )
    session.add(relation)
    await session.flush()
    if created_at is not None:
        relation.created_at = created_at
        await session.flush()
    return relation


@pytest.mark.asyncio
async def test_ensure_hypothesis_entity_creates_entity_and_writes_back(
    db_session: AsyncSession,
) -> None:
    hypothesis = await _seed_hypothesis(db_session)
    entity_id = await ensure_hypothesis_entity(
        session=db_session, hypothesis=hypothesis
    )
    assert hypothesis.entity_id == entity_id
    entity = (
        await db_session.execute(select(Entity).where(Entity.id == entity_id))
    ).scalar_one()
    assert entity.type == EntityType.hypothesis.value
    assert entity.canonical_name == hypothesis.claim_text
    assert entity.external_ids == {"hypothesis_id": str(hypothesis.id)}


@pytest.mark.asyncio
async def test_mirror_entity_resolves_via_exact_alias_match_against_similar_claims(
    db_session: AsyncSession,
) -> None:
    """The mirror entity must seed `aliases` with the claim text so the
    resolver's exact-alias step (step 1) returns it directly. Otherwise the
    candidate falls through to fuzzy match, where two near-identical
    hypotheses can score over the ambiguity margin and the resolver creates
    a duplicate entity — leaving the relation pointing at the wrong
    hypothesis.
    """
    similar_claim = "Energy sector outperforms over next twelve weeks"
    near_duplicate = "Energy sector outperforms over the next 12 weeks"

    hypothesis_a = await _seed_hypothesis(db_session, claim_text=similar_claim)
    hypothesis_b = await _seed_hypothesis(db_session, claim_text=near_duplicate)
    entity_a = await ensure_hypothesis_entity(
        session=db_session, hypothesis=hypothesis_a
    )
    entity_b = await ensure_hypothesis_entity(
        session=db_session, hypothesis=hypothesis_b
    )
    await db_session.flush()

    candidate = CandidateEntity(
        text_span=similar_claim,
        suggested_type=EntityTypeEnum.hypothesis,
        context_excerpt="…paragraph mentioning the claim verbatim…",
        exact_quote=similar_claim,
        chunk_id=uuid.uuid4(),
        extraction_confidence=0.9,
    )
    outcome = await resolve_candidate(session=db_session, candidate=candidate)

    assert outcome.chosen_entity_id == entity_a
    assert outcome.chosen_entity_id != entity_b

    hypothesis_entity_count = (
        await db_session.execute(
            select(Entity).where(Entity.type == EntityType.hypothesis.value)
        )
    ).scalars().all()
    assert len(hypothesis_entity_count) == 2


@pytest.mark.asyncio
async def test_ensure_hypothesis_entity_is_idempotent(
    db_session: AsyncSession,
) -> None:
    hypothesis = await _seed_hypothesis(db_session)
    first = await ensure_hypothesis_entity(
        session=db_session, hypothesis=hypothesis
    )
    second = await ensure_hypothesis_entity(
        session=db_session, hypothesis=hypothesis
    )
    assert first == second
    entities = (
        await db_session.execute(
            select(Entity).where(Entity.type == EntityType.hypothesis.value)
        )
    ).scalars().all()
    assert len(entities) == 1


@pytest.mark.asyncio
async def test_recompute_returns_none_when_hypothesis_missing_entity(
    db_session: AsyncSession,
) -> None:
    hypothesis = await _seed_hypothesis(db_session)
    result = await recompute_belief_for_hypothesis(
        session=db_session, hypothesis_id=hypothesis.id
    )
    assert result is None


@pytest.mark.asyncio
async def test_recompute_with_no_relations_yields_neutral_belief(
    db_session: AsyncSession,
) -> None:
    hypothesis = await _seed_hypothesis(db_session)
    await ensure_hypothesis_entity(session=db_session, hypothesis=hypothesis)
    result = await recompute_belief_for_hypothesis(
        session=db_session, hypothesis_id=hypothesis.id
    )
    assert result is not None
    assert result.belief == 0.5
    await db_session.refresh(hypothesis)
    assert hypothesis.belief == 0.5
    assert len(hypothesis.belief_history) == 1
    history_entry = hypothesis.belief_history[0]
    assert history_entry["method"] == BELIEF_COMPUTATION_METHOD
    assert history_entry["belief"] == 0.5
    assert history_entry["input_count"] == 0


@pytest.mark.asyncio
async def test_recompute_with_supporting_relation_yields_high_belief(
    db_session: AsyncSession,
) -> None:
    hypothesis = await _seed_hypothesis(db_session)
    hypothesis_entity_id = await ensure_hypothesis_entity(
        session=db_session, hypothesis=hypothesis
    )
    source_entity = await _seed_entity(db_session, name="AAPL")
    await _write_belief_relation(
        db_session,
        from_entity_id=source_entity.id,
        hypothesis_entity_id=hypothesis_entity_id,
        relation_type=RelationType.supports_hypothesis,
        sign=1.0,
        reliability_score=1.0,
    )
    result = await recompute_belief_for_hypothesis(
        session=db_session, hypothesis_id=hypothesis.id
    )
    assert result is not None
    assert result.belief == pytest.approx(1.0)

    audit = (
        await db_session.execute(
            select(BeliefRecomputation).where(
                BeliefRecomputation.hypothesis_id == hypothesis.id
            )
        )
    ).scalars().all()
    assert len(audit) == 1
    audit_row = audit[0]
    assert audit_row.belief == pytest.approx(1.0)
    assert audit_row.computation_method == BELIEF_COMPUTATION_METHOD
    assert audit_row.inputs is not None
    assert len(audit_row.inputs) == 1
    assert audit_row.inputs[0]["sign"] == 1.0
    assert audit_row.inputs[0]["reliability"] == 1.0
    assert audit_row.contributing_evidence_ids
    assert len(audit_row.contributing_evidence_ids) == 1


@pytest.mark.asyncio
async def test_recompute_with_contradicting_relation_yields_low_belief(
    db_session: AsyncSession,
) -> None:
    hypothesis = await _seed_hypothesis(db_session)
    hypothesis_entity_id = await ensure_hypothesis_entity(
        session=db_session, hypothesis=hypothesis
    )
    source_entity = await _seed_entity(db_session, name="MSFT")
    await _write_belief_relation(
        db_session,
        from_entity_id=source_entity.id,
        hypothesis_entity_id=hypothesis_entity_id,
        relation_type=RelationType.contradicts_hypothesis,
        sign=-1.0,
        reliability_score=1.0,
    )
    result = await recompute_belief_for_hypothesis(
        session=db_session, hypothesis_id=hypothesis.id
    )
    assert result is not None
    assert result.belief == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_recompute_balances_supporting_and_contradicting_evidence(
    db_session: AsyncSession,
) -> None:
    hypothesis = await _seed_hypothesis(db_session)
    hypothesis_entity_id = await ensure_hypothesis_entity(
        session=db_session, hypothesis=hypothesis
    )
    source = await _seed_entity(db_session, name="news source")
    await _write_belief_relation(
        db_session,
        from_entity_id=source.id,
        hypothesis_entity_id=hypothesis_entity_id,
        relation_type=RelationType.supports_hypothesis,
        sign=1.0,
        confidence=0.8,
    )
    await _write_belief_relation(
        db_session,
        from_entity_id=source.id,
        hypothesis_entity_id=hypothesis_entity_id,
        relation_type=RelationType.contradicts_hypothesis,
        sign=-1.0,
        confidence=0.8,
    )
    result = await recompute_belief_for_hypothesis(
        session=db_session, hypothesis_id=hypothesis.id
    )
    assert result is not None
    assert result.belief == pytest.approx(0.5)
    assert len(result.contributions) == 2


@pytest.mark.asyncio
async def test_recompute_uses_default_reliability_when_source_missing(
    db_session: AsyncSession,
) -> None:
    hypothesis = await _seed_hypothesis(db_session)
    hypothesis_entity_id = await ensure_hypothesis_entity(
        session=db_session, hypothesis=hypothesis
    )
    source = await _seed_entity(db_session, name="source")
    await _write_belief_relation(
        db_session,
        from_entity_id=source.id,
        hypothesis_entity_id=hypothesis_entity_id,
        relation_type=RelationType.supports_hypothesis,
        sign=1.0,
        reliability_score=None,
    )
    result = await recompute_belief_for_hypothesis(
        session=db_session, hypothesis_id=hypothesis.id
    )
    assert result is not None
    assert result.contributions[0].reliability == 1.0
    assert result.belief > 0.5


@pytest.mark.asyncio
async def test_recompute_beliefs_for_relations_ignores_non_belief_types(
    db_session: AsyncSession,
) -> None:
    hypothesis = await _seed_hypothesis(db_session)
    hypothesis_entity_id = await ensure_hypothesis_entity(
        session=db_session, hypothesis=hypothesis
    )
    source = await _seed_entity(db_session, name="source")
    competes = Relation(
        from_id=source.id,
        to_id=hypothesis_entity_id,
        type=RelationType.competes_with.value,
        attributes={},
        sign=1.0,
    )
    db_session.add(competes)
    await db_session.flush()

    affected = await recompute_beliefs_for_relations(
        session=db_session, relation_ids=[competes.id]
    )
    assert affected == {}


@pytest.mark.asyncio
async def test_recompute_beliefs_for_relations_runs_for_each_matching_hypothesis(
    db_session: AsyncSession,
) -> None:
    hypothesis_a = await _seed_hypothesis(db_session, claim_text="claim A")
    hypothesis_b = await _seed_hypothesis(db_session, claim_text="claim B")
    entity_a = await ensure_hypothesis_entity(
        session=db_session, hypothesis=hypothesis_a
    )
    entity_b = await ensure_hypothesis_entity(
        session=db_session, hypothesis=hypothesis_b
    )
    source = await _seed_entity(db_session, name="source")
    relation_a = await _write_belief_relation(
        db_session,
        from_entity_id=source.id,
        hypothesis_entity_id=entity_a,
        relation_type=RelationType.supports_hypothesis,
        sign=1.0,
    )
    relation_b = await _write_belief_relation(
        db_session,
        from_entity_id=source.id,
        hypothesis_entity_id=entity_b,
        relation_type=RelationType.contradicts_hypothesis,
        sign=-1.0,
    )

    affected = await recompute_beliefs_for_relations(
        session=db_session,
        relation_ids=[relation_a.id, relation_b.id],
    )
    assert set(affected.keys()) == {hypothesis_a.id, hypothesis_b.id}
    assert affected[hypothesis_a.id].belief == pytest.approx(1.0)
    assert affected[hypothesis_b.id].belief == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_recompute_uses_explicit_relevance_when_set(
    db_session: AsyncSession,
) -> None:
    hypothesis = await _seed_hypothesis(db_session)
    hypothesis_entity_id = await ensure_hypothesis_entity(
        session=db_session, hypothesis=hypothesis
    )
    source = await _seed_entity(db_session, name="src")
    await _write_belief_relation(
        db_session,
        from_entity_id=source.id,
        hypothesis_entity_id=hypothesis_entity_id,
        relation_type=RelationType.supports_hypothesis,
        sign=1.0,
        relevance=0.25,
    )
    result = await recompute_belief_for_hypothesis(
        session=db_session, hypothesis_id=hypothesis.id
    )
    assert result is not None
    assert result.contributions[0].relevance == 0.25


@pytest.mark.asyncio
async def test_recompute_records_decay_for_older_evidence(
    db_session: AsyncSession,
) -> None:
    hypothesis = await _seed_hypothesis(db_session)
    hypothesis_entity_id = await ensure_hypothesis_entity(
        session=db_session, hypothesis=hypothesis
    )
    source = await _seed_entity(db_session, name="src")
    now = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)
    await _write_belief_relation(
        db_session,
        from_entity_id=source.id,
        hypothesis_entity_id=hypothesis_entity_id,
        relation_type=RelationType.supports_hypothesis,
        sign=1.0,
        created_at=now - timedelta(days=180),
    )
    result = await recompute_belief_for_hypothesis(
        session=db_session, hypothesis_id=hypothesis.id, now=now
    )
    assert result is not None
    contribution = result.contributions[0]
    assert contribution.age_days == pytest.approx(180.0)
    assert contribution.decay < 1.0
