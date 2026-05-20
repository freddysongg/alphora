"""Belief recomputation pipeline (session-bound).

Hypotheses are mirrored as `Entity` rows (`type=hypothesis`) so that a
`supports_hypothesis` / `contradicts_hypothesis` relation can use the
hypothesis-entity as its `to_id` — keeping the entity graph as the single
addressable substrate while still letting the belief engine join back to
the `Hypothesis` row for state tracking.

This module exposes three entry points:

- `ensure_hypothesis_entity` — idempotently create the mirror Entity for a
  Hypothesis and write `hypothesis.entity_id`.
- `recompute_belief_for_hypothesis` — query supporting / contradicting
  relations for a hypothesis, run `weighted_avg_decay_v1`, persist the
  scalar `belief`, append to `belief_history` and write the audit row.
- `recompute_beliefs_for_relations` — given a set of just-written relation
  ids, recompute belief for every affected hypothesis.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import (
    BeliefRecomputation,
    DataSource,
    Entity,
    EntityType,
    Evidence,
    Hypothesis,
    Relation,
    RelationType,
)
from app.services.belief.recompute import (
    BELIEF_COMPUTATION_METHOD,
    DEFAULT_HALF_LIFE_DAYS,
    BeliefInput,
    BeliefRecomputeResult,
    weighted_avg_decay_v1,
)

_BELIEF_SUPPORT_TYPES: Final[frozenset[str]] = frozenset(
    {
        RelationType.supports_hypothesis.value,
        RelationType.contradicts_hypothesis.value,
    }
)


async def ensure_hypothesis_entity(
    *,
    session: AsyncSession,
    hypothesis: Hypothesis,
) -> uuid.UUID:
    """Mirror a Hypothesis as an Entity and write `hypothesis.entity_id`.

    The claim text is seeded into `aliases` so the entity resolver's
    exact-alias step (step 1) returns the mirror directly. Without this,
    a candidate with `text_span == claim_text` falls through to fuzzy
    matching, where two near-identical claims can both score over the
    ambiguity margin and the resolver creates a duplicate hypothesis
    entity — leaving the relation pointing at the wrong row.

    Idempotent — returns the existing `entity_id` when already set.
    """
    if hypothesis.entity_id is not None:
        return hypothesis.entity_id

    entity = Entity(
        type=EntityType.hypothesis.value,
        canonical_name=hypothesis.claim_text,
        aliases=[hypothesis.claim_text],
        external_ids={"hypothesis_id": str(hypothesis.id)},
        attributes={"created_by": "belief_engine_v1"},
        confidence=1.0,
        needs_review=False,
    )
    session.add(entity)
    await session.flush()
    hypothesis.entity_id = entity.id
    return entity.id


async def recompute_belief_for_hypothesis(
    *,
    session: AsyncSession,
    hypothesis_id: uuid.UUID,
    now: datetime | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> BeliefRecomputeResult | None:
    """Recompute belief for one hypothesis and persist the result.

    Returns `None` when the hypothesis has no mirror entity yet (so no
    supports/contradicts relations can target it) — the recomputation is a
    no-op in that case. Otherwise persists the scalar `belief`, appends a
    history entry and writes a `belief_recomputations` row.
    """
    hypothesis = (
        await session.execute(
            select(Hypothesis).where(Hypothesis.id == hypothesis_id)
        )
    ).scalar_one_or_none()
    if hypothesis is None or hypothesis.entity_id is None:
        return None

    inputs = await _load_belief_inputs(
        session=session, hypothesis_entity_id=hypothesis.entity_id
    )
    effective_now = now if now is not None else datetime.now(UTC)
    result = weighted_avg_decay_v1(
        inputs, now=effective_now, half_life_days=half_life_days
    )

    hypothesis.belief = result.belief
    history = list(hypothesis.belief_history or [])
    history.append(
        {
            "computed_at": effective_now.isoformat(),
            "belief": result.belief,
            "method": BELIEF_COMPUTATION_METHOD,
            "input_count": len(result.contributions),
            "total_weight": result.total_weight,
        }
    )
    hypothesis.belief_history = history

    recomputation = BeliefRecomputation(
        hypothesis_id=hypothesis.id,
        computed_at=effective_now,
        belief=result.belief,
        contributing_evidence_ids=[
            str(contribution.source_id)
            for contribution in result.contributions
            if contribution.source_id is not None
        ],
        computation_method=BELIEF_COMPUTATION_METHOD,
        inputs=[contribution.to_jsonable() for contribution in result.contributions],
    )
    session.add(recomputation)
    await session.flush()
    return result


async def recompute_beliefs_for_relations(
    *,
    session: AsyncSession,
    relation_ids: Iterable[uuid.UUID],
    now: datetime | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> dict[uuid.UUID, BeliefRecomputeResult]:
    """Recompute belief for every hypothesis affected by these relations.

    A relation only triggers recomputation when its type is
    `supports_hypothesis` or `contradicts_hypothesis` and its `to_id`
    matches a `Hypothesis.entity_id`. Returns a map of hypothesis_id →
    result for inspection / testing; an empty map means nothing was
    affected.
    """
    ids = [rid for rid in relation_ids]
    if not ids:
        return {}

    relations = (
        (
            await session.execute(
                select(Relation).where(
                    Relation.id.in_(ids),
                    Relation.type.in_(_BELIEF_SUPPORT_TYPES),
                )
            )
        )
        .scalars()
        .all()
    )
    if not relations:
        return {}

    entity_ids = {relation.to_id for relation in relations}
    hypotheses = (
        (
            await session.execute(
                select(Hypothesis).where(Hypothesis.entity_id.in_(entity_ids))
            )
        )
        .scalars()
        .all()
    )

    results: dict[uuid.UUID, BeliefRecomputeResult] = {}
    for hypothesis in hypotheses:
        result = await recompute_belief_for_hypothesis(
            session=session,
            hypothesis_id=hypothesis.id,
            now=now,
            half_life_days=half_life_days,
        )
        if result is not None:
            results[hypothesis.id] = result
    return results


async def _load_belief_inputs(
    *,
    session: AsyncSession,
    hypothesis_entity_id: uuid.UUID,
) -> list[BeliefInput]:
    """Join supports/contradicts relations with evidence + data source.

    A LEFT OUTER JOIN on evidence and data_sources means relations without
    a resolved source still contribute — they fall back to the default
    reliability (1.0) so the formula doesn't silently drop them.
    """
    stmt = (
        select(Relation, Evidence, DataSource)
        .outerjoin(Evidence, Relation.source_id == Evidence.id)
        .outerjoin(DataSource, Evidence.source_id == DataSource.id)
        .where(
            Relation.to_id == hypothesis_entity_id,
            Relation.type.in_(_BELIEF_SUPPORT_TYPES),
        )
        .order_by(Relation.created_at.asc(), Relation.id.asc())
    )
    rows = (await session.execute(stmt)).all()

    inputs: list[BeliefInput] = []
    for relation, _evidence, data_source in rows:
        reliability = (
            data_source.reliability_score if data_source is not None else 1.0
        )
        confidence = (
            relation.extraction_confidence
            if relation.extraction_confidence is not None
            else 0.5
        )
        relevance = (
            relation.relevance
            if relation.relevance is not None
            else (1.0 if relation.is_explicit else 0.6)
        )
        inputs.append(
            BeliefInput(
                relation_id=relation.id,
                relation_type=relation.type,
                from_id=relation.from_id,
                to_id=relation.to_id,
                source_id=relation.source_id,
                chunk_id=relation.chunk_id,
                quote=relation.quote,
                is_explicit=relation.is_explicit,
                sign=relation.sign,
                reliability=reliability,
                confidence=confidence,
                relevance=relevance,
                created_at=_aware(relation.created_at),
            )
        )
    return inputs


def _aware(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; normalize to UTC-aware."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


__all__ = [
    "ensure_hypothesis_entity",
    "recompute_belief_for_hypothesis",
    "recompute_beliefs_for_relations",
]
