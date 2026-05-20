import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import (
    Entity,
    EntityType,
    EventResolution,
    Hypothesis,
    HypothesisStatus,
    Relation,
    RelationType,
)
from app.services.belief import ensure_hypothesis_entity
from app.services.hypothesis.events import (
    InvalidEventResolutionKindError,
    apply_event_resolution,
    apply_outcome_to_hypothesis,
    record_event_resolution,
)


async def _seed_event(
    session: AsyncSession, *, name: str = "Q3 earnings"
) -> Entity:
    entity = Entity(
        type=EntityType.event.value,
        canonical_name=name,
        aliases=[name],
        external_ids={},
        attributes={},
    )
    session.add(entity)
    await session.flush()
    return entity


async def _seed_hypothesis_with_entity(
    session: AsyncSession,
    *,
    claim_text: str,
    status_value: str = HypothesisStatus.active.value,
) -> Hypothesis:
    row = Hypothesis(
        claim_text=claim_text,
        scope_entity_ids=[],
        scope_theme_ids=[],
        status=status_value,
    )
    session.add(row)
    await session.flush()
    await ensure_hypothesis_entity(session=session, hypothesis=row)
    return row


async def _add_conditional_edge(
    session: AsyncSession,
    *,
    event: Entity,
    hypothesis_entity_id: uuid.UUID,
    relation_type: RelationType,
) -> Relation:
    relation = Relation(
        from_id=event.id,
        to_id=hypothesis_entity_id,
        type=relation_type.value,
        attributes={},
        is_explicit=True,
        sign=1.0,
    )
    session.add(relation)
    await session.flush()
    return relation


@pytest.mark.asyncio
async def test_record_event_resolution_persists_row(
    db_session: AsyncSession,
) -> None:
    event = await _seed_event(db_session)
    resolved_at = datetime(2026, 6, 1, 14, 0, tzinfo=UTC)
    row = await record_event_resolution(
        session=db_session,
        event_entity_id=event.id,
        kind="beat",
        resolved_at=resolved_at,
        notes="exceeded EPS by 5%",
        payload={"eps_actual": 2.15, "eps_consensus": 2.05},
    )
    await db_session.commit()
    refreshed = (
        await db_session.execute(
            select(EventResolution).where(EventResolution.id == row.id)
        )
    ).scalar_one()
    assert refreshed.event_entity_id == event.id
    assert refreshed.kind == "beat"
    assert refreshed.resolved_at == resolved_at
    assert refreshed.notes == "exceeded EPS by 5%"
    assert refreshed.payload == {"eps_actual": 2.15, "eps_consensus": 2.05}


@pytest.mark.asyncio
async def test_record_event_resolution_defaults_to_now_when_resolved_at_missing(
    db_session: AsyncSession,
) -> None:
    event = await _seed_event(db_session)
    row = await record_event_resolution(
        session=db_session,
        event_entity_id=event.id,
        kind="miss",
    )
    await db_session.commit()
    assert row.resolved_at is not None


@pytest.mark.asyncio
async def test_record_event_resolution_rejects_unknown_kind(
    db_session: AsyncSession,
) -> None:
    event = await _seed_event(db_session)
    with pytest.raises(InvalidEventResolutionKindError):
        await record_event_resolution(
            session=db_session,
            event_entity_id=event.id,
            kind="explosion",
        )


@pytest.mark.asyncio
async def test_apply_event_resolution_validates_bound_hypothesis_on_beat(
    db_session: AsyncSession,
) -> None:
    event = await _seed_event(db_session)
    hypothesis = await _seed_hypothesis_with_entity(
        db_session, claim_text="NVDA beats consensus"
    )
    assert hypothesis.entity_id is not None
    await _add_conditional_edge(
        db_session,
        event=event,
        hypothesis_entity_id=hypothesis.entity_id,
        relation_type=RelationType.validates_if_beat,
    )
    await db_session.commit()

    resolution = await record_event_resolution(
        session=db_session, event_entity_id=event.id, kind="beat"
    )
    outcome = await apply_event_resolution(
        session=db_session, resolution=resolution
    )
    await db_session.commit()

    assert hypothesis.id in outcome.validated_hypothesis_ids
    refreshed = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == hypothesis.id)
        )
    ).scalar_one()
    assert refreshed.status == HypothesisStatus.validated.value
    assert refreshed.last_activity_at is not None


@pytest.mark.asyncio
async def test_apply_event_resolution_falsifies_on_miss(
    db_session: AsyncSession,
) -> None:
    event = await _seed_event(db_session)
    hypothesis = await _seed_hypothesis_with_entity(
        db_session, claim_text="NVDA misses consensus"
    )
    assert hypothesis.entity_id is not None
    await _add_conditional_edge(
        db_session,
        event=event,
        hypothesis_entity_id=hypothesis.entity_id,
        relation_type=RelationType.falsifies_if_miss,
    )
    await db_session.commit()

    resolution = await record_event_resolution(
        session=db_session, event_entity_id=event.id, kind="miss"
    )
    outcome = await apply_event_resolution(
        session=db_session, resolution=resolution
    )
    await db_session.commit()

    assert hypothesis.id in outcome.falsified_hypothesis_ids
    refreshed = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == hypothesis.id)
        )
    ).scalar_one()
    assert refreshed.status == HypothesisStatus.falsified.value


@pytest.mark.asyncio
async def test_apply_event_resolution_skips_terminal_hypotheses(
    db_session: AsyncSession,
) -> None:
    event = await _seed_event(db_session)
    hypothesis = await _seed_hypothesis_with_entity(
        db_session,
        claim_text="already validated",
        status_value=HypothesisStatus.validated.value,
    )
    assert hypothesis.entity_id is not None
    await _add_conditional_edge(
        db_session,
        event=event,
        hypothesis_entity_id=hypothesis.entity_id,
        relation_type=RelationType.validates_if_beat,
    )
    await db_session.commit()

    resolution = await record_event_resolution(
        session=db_session, event_entity_id=event.id, kind="beat"
    )
    outcome = await apply_event_resolution(
        session=db_session, resolution=resolution
    )
    await db_session.commit()
    assert hypothesis.id in outcome.skipped_hypothesis_ids
    assert hypothesis.id not in outcome.validated_hypothesis_ids


@pytest.mark.asyncio
async def test_apply_event_resolution_ignores_mismatched_edge_for_beat(
    db_session: AsyncSession,
) -> None:
    """`falsifies_if_miss` is *not* triggered by a `beat` resolution."""
    event = await _seed_event(db_session)
    hypothesis = await _seed_hypothesis_with_entity(
        db_session, claim_text="should not transition"
    )
    assert hypothesis.entity_id is not None
    await _add_conditional_edge(
        db_session,
        event=event,
        hypothesis_entity_id=hypothesis.entity_id,
        relation_type=RelationType.falsifies_if_miss,
    )
    await db_session.commit()

    resolution = await record_event_resolution(
        session=db_session, event_entity_id=event.id, kind="beat"
    )
    outcome = await apply_event_resolution(
        session=db_session, resolution=resolution
    )
    await db_session.commit()
    assert outcome.validated_hypothesis_ids == []
    assert outcome.falsified_hypothesis_ids == []
    refreshed = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == hypothesis.id)
        )
    ).scalar_one()
    assert refreshed.status == HypothesisStatus.active.value


@pytest.mark.asyncio
async def test_apply_event_resolution_no_op_on_neutral(
    db_session: AsyncSession,
) -> None:
    event = await _seed_event(db_session)
    hypothesis = await _seed_hypothesis_with_entity(
        db_session, claim_text="neutral case"
    )
    assert hypothesis.entity_id is not None
    await _add_conditional_edge(
        db_session,
        event=event,
        hypothesis_entity_id=hypothesis.entity_id,
        relation_type=RelationType.validates_if_beat,
    )
    await db_session.commit()

    resolution = await record_event_resolution(
        session=db_session, event_entity_id=event.id, kind="neutral"
    )
    outcome = await apply_event_resolution(
        session=db_session, resolution=resolution
    )
    await db_session.commit()
    assert outcome.validated_hypothesis_ids == []
    assert outcome.falsified_hypothesis_ids == []
    assert outcome.skipped_hypothesis_ids == []


@pytest.mark.asyncio
async def test_apply_event_resolution_fans_out_to_multiple_hypotheses(
    db_session: AsyncSession,
) -> None:
    event = await _seed_event(db_session)
    hyp_a = await _seed_hypothesis_with_entity(
        db_session, claim_text="first hypothesis"
    )
    hyp_b = await _seed_hypothesis_with_entity(
        db_session, claim_text="second hypothesis"
    )
    assert hyp_a.entity_id is not None
    assert hyp_b.entity_id is not None
    await _add_conditional_edge(
        db_session,
        event=event,
        hypothesis_entity_id=hyp_a.entity_id,
        relation_type=RelationType.validates_if_beat,
    )
    await _add_conditional_edge(
        db_session,
        event=event,
        hypothesis_entity_id=hyp_b.entity_id,
        relation_type=RelationType.validates_if_beat,
    )
    await db_session.commit()

    resolution = await record_event_resolution(
        session=db_session, event_entity_id=event.id, kind="beat"
    )
    outcome = await apply_event_resolution(
        session=db_session, resolution=resolution
    )
    await db_session.commit()
    assert set(outcome.validated_hypothesis_ids) == {hyp_a.id, hyp_b.id}


def test_apply_outcome_to_hypothesis_returns_false_for_terminal() -> None:
    row = Hypothesis(
        claim_text="terminal",
        scope_entity_ids=[],
        scope_theme_ids=[],
        status=HypothesisStatus.expired.value,
    )
    out = apply_outcome_to_hypothesis(
        hypothesis=row,
        transition_to=HypothesisStatus.validated.value,
        now=datetime(2026, 6, 1, tzinfo=UTC),
    )
    assert out is False
    assert row.status == HypothesisStatus.expired.value


def test_apply_outcome_to_hypothesis_transitions_open_row() -> None:
    row = Hypothesis(
        claim_text="open",
        scope_entity_ids=[],
        scope_theme_ids=[],
        status=HypothesisStatus.active.value,
    )
    out = apply_outcome_to_hypothesis(
        hypothesis=row,
        transition_to=HypothesisStatus.validated.value,
        now=datetime(2026, 6, 1, tzinfo=UTC),
    )
    assert out is True
    assert row.status == HypothesisStatus.validated.value
    assert row.last_activity_at == datetime(2026, 6, 1, tzinfo=UTC)
