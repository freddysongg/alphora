"""Event-resolution ingestion + fan-out to bound hypotheses (Phase 4).

The graph carries conditional edges from event entities to hypothesis
entities. Today we model two:

- `validates_if_beat` — if the event "beats", the linked hypothesis is
  validated.
- `falsifies_if_miss` — if the event "misses", the linked hypothesis is
  falsified.

`record_event_resolution` persists an `EventResolution` row; the linked
hypothesis transitions only happen when `apply_event_resolution` runs (or
when the caller uses `record_event_resolution(..., apply=True)`). The split
keeps the storage path independent of the state-machine path so a backfill
can replay resolutions without re-triggering side-effects on hypotheses
that have since reached a terminal state.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import (
    EventResolution,
    EventResolutionKind,
    Hypothesis,
    HypothesisStatus,
    Relation,
    RelationType,
)

_TERMINAL_STATES: Final[frozenset[str]] = frozenset(
    {
        HypothesisStatus.validated.value,
        HypothesisStatus.falsified.value,
        HypothesisStatus.expired.value,
        HypothesisStatus.superseded.value,
    }
)


@dataclass(frozen=True)
class EventResolutionOutcome:
    resolution_id: uuid.UUID
    validated_hypothesis_ids: list[uuid.UUID] = field(default_factory=list)
    falsified_hypothesis_ids: list[uuid.UUID] = field(default_factory=list)
    skipped_hypothesis_ids: list[uuid.UUID] = field(default_factory=list)


async def record_event_resolution(
    *,
    session: AsyncSession,
    event_entity_id: uuid.UUID,
    kind: str,
    resolved_at: datetime | None = None,
    source_id: uuid.UUID | None = None,
    notes: str | None = None,
    payload: dict[str, object] | None = None,
) -> EventResolution:
    """Persist an `EventResolution` row. Does not apply side-effects.

    `kind` is validated against `EventResolutionKind` so callers cannot
    persist a value the fan-out logic doesn't know how to read. Use
    `apply_event_resolution` to roll the side-effects forward.
    """
    normalized_kind = _normalize_kind(kind)
    row = EventResolution(
        event_entity_id=event_entity_id,
        kind=normalized_kind.value,
        resolved_at=resolved_at or datetime.now(UTC),
        source_id=source_id,
        notes=notes,
        payload=payload,
    )
    session.add(row)
    await session.flush()
    return row


async def apply_event_resolution(
    *,
    session: AsyncSession,
    resolution: EventResolution,
    now: datetime | None = None,
) -> EventResolutionOutcome:
    """Walk every conditional edge from the event and apply its action.

    A `beat` resolution validates every hypothesis on the receiving end of
    a `validates_if_beat` edge from this event. A `miss` resolution
    falsifies every hypothesis on the receiving end of a `falsifies_if_miss`
    edge. `neutral` resolutions persist but do not transition anything;
    they're for follow-up review.

    Hypotheses already in a terminal state (`validated`, `falsified`,
    `expired`, `superseded`) are skipped — the audit trail in
    `belief_history` plus the original `EventResolution` row already
    capture that a resolution arrived; mutating an already-settled row
    would lose the original verdict.
    """
    kind = _normalize_kind(resolution.kind)
    effective_now = now if now is not None else datetime.now(UTC)
    outcome = EventResolutionOutcome(resolution_id=resolution.id)
    if kind is EventResolutionKind.neutral:
        return outcome

    target_type = (
        RelationType.validates_if_beat.value
        if kind is EventResolutionKind.beat
        else RelationType.falsifies_if_miss.value
    )
    transition_to = (
        HypothesisStatus.validated.value
        if kind is EventResolutionKind.beat
        else HypothesisStatus.falsified.value
    )

    hypothesis_entity_ids = await _conditional_target_entity_ids(
        session=session,
        event_entity_id=resolution.event_entity_id,
        relation_type=target_type,
    )
    if not hypothesis_entity_ids:
        return outcome

    hypotheses = await _load_hypotheses_by_entity_ids(
        session=session, entity_ids=hypothesis_entity_ids
    )
    for hypothesis in hypotheses:
        applied = apply_outcome_to_hypothesis(
            hypothesis=hypothesis,
            transition_to=transition_to,
            now=effective_now,
        )
        if not applied:
            outcome.skipped_hypothesis_ids.append(hypothesis.id)
            continue
        if kind is EventResolutionKind.beat:
            outcome.validated_hypothesis_ids.append(hypothesis.id)
        else:
            outcome.falsified_hypothesis_ids.append(hypothesis.id)
    return outcome


def apply_outcome_to_hypothesis(
    *,
    hypothesis: Hypothesis,
    transition_to: str,
    now: datetime,
) -> bool:
    """Transition one hypothesis to `transition_to` if it is still open.

    Returns True when the hypothesis was actually transitioned. Returns
    False when the row was already in a terminal state — the caller treats
    this as "audited, not mutated" and records the skip.
    """
    if hypothesis.status in _TERMINAL_STATES:
        return False
    hypothesis.status = transition_to
    hypothesis.last_activity_at = now
    return True


async def _conditional_target_entity_ids(
    *,
    session: AsyncSession,
    event_entity_id: uuid.UUID,
    relation_type: str,
) -> list[uuid.UUID]:
    rows = (
        (
            await session.execute(
                select(Relation.to_id).where(
                    Relation.from_id == event_entity_id,
                    Relation.type == relation_type,
                )
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def _load_hypotheses_by_entity_ids(
    *,
    session: AsyncSession,
    entity_ids: Sequence[uuid.UUID],
) -> list[Hypothesis]:
    if not entity_ids:
        return []
    rows = (
        (
            await session.execute(
                select(Hypothesis).where(Hypothesis.entity_id.in_(entity_ids))
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def _normalize_kind(kind: str) -> EventResolutionKind:
    try:
        return EventResolutionKind(kind)
    except ValueError as exc:
        raise InvalidEventResolutionKindError(
            f"unknown event resolution kind: {kind!r}"
        ) from exc


class InvalidEventResolutionKindError(ValueError):
    """Raised when an event resolution kind is not in `EventResolutionKind`."""


__all__ = [
    "EventResolutionOutcome",
    "InvalidEventResolutionKindError",
    "apply_event_resolution",
    "apply_outcome_to_hypothesis",
    "record_event_resolution",
]
