import base64
import binascii
import uuid
from datetime import UTC, datetime
from typing import Annotated, Final

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.db.models_graph import (
    BeliefRecomputation,
    Entity,
    EventResolution,
    Hypothesis,
    HypothesisStatus,
    Relation,
    RelationType,
)
from app.db.models_runs import RunEventLevel
from app.schemas.graph import (
    BeliefInputBreakdown,
    BeliefRecomputationPublic,
    EventResolutionPublic,
)
from app.schemas.hypotheses import (
    ConditionalEdgePublic,
    HypothesisBeliefResponse,
    HypothesisHistoryResponse,
    HypothesisLifecycleResponse,
    HypothesisListResponse,
    HypothesisParentRequest,
    HypothesisPublic,
    HypothesisState,
    HypothesisStateFilter,
    HypothesisTransitionRequest,
    LifecycleSweepCounts,
    LifecycleSweepResponse,
)
from app.services.hypothesis import run_lifecycle_sweep
from app.services.run_events import emit_run_event

router = APIRouter()

_HYPOTHESIS_ACTIVATED_EVENT = "hypothesis_activated"
_HYPOTHESIS_TRANSITIONED_EVENT = "hypothesis_transitioned"

_CONDITIONAL_RELATION_TYPES: Final[frozenset[str]] = frozenset(
    {
        RelationType.validates_if_beat.value,
        RelationType.falsifies_if_miss.value,
    }
)

_ALLOWED_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    HypothesisStatus.proposed.value: frozenset(
        {
            HypothesisStatus.active.value,
            HypothesisStatus.expired.value,
            HypothesisStatus.superseded.value,
        }
    ),
    HypothesisStatus.active.value: frozenset(
        {
            HypothesisStatus.validated.value,
            HypothesisStatus.falsified.value,
            HypothesisStatus.expired.value,
            HypothesisStatus.superseded.value,
        }
    ),
}

_RECENT_RESOLUTIONS_LIMIT: Final[int] = 10


def _encode_cursor(created_at: datetime, hypothesis_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{hypothesis_id}".encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii")
        created_at_raw, id_raw = decoded.split("|", maxsplit=1)
        return datetime.fromisoformat(created_at_raw), uuid.UUID(id_raw)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid cursor",
        ) from exc


def _to_public(row: Hypothesis) -> HypothesisPublic:
    return HypothesisPublic(
        id=row.id,
        claim_text=row.claim_text,
        state=HypothesisState(row.status),
        scope_entity_ids=[uuid.UUID(s) for s in row.scope_entity_ids or []],
        scope_theme_ids=[uuid.UUID(s) for s in row.scope_theme_ids or []],
        source_run_id=row.proposed_by_run_id,
        entity_id=row.entity_id,
        belief=row.belief,
        belief_history=list(row.belief_history or []),
        parent_hypothesis_id=row.parent_hypothesis_id,
        superseded_by_id=row.superseded_by_id,
        last_activity_at=row.last_activity_at,
        stagnation_flagged_at=row.stagnation_flagged_at,
        archived_at=row.archived_at,
        archived_reason=row.archived_reason,
        valid_until=row.valid_until,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/hypotheses", response_model=HypothesisListResponse)
async def list_hypotheses(
    session: SessionDep,
    state: HypothesisStateFilter = HypothesisStateFilter.all,
    run_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> HypothesisListResponse:
    stmt = select(Hypothesis)
    if state is HypothesisStateFilter.proposed:
        stmt = stmt.where(Hypothesis.status == HypothesisStatus.proposed.value)
    elif state is HypothesisStateFilter.active:
        stmt = stmt.where(Hypothesis.status == HypothesisStatus.active.value)
    if run_id is not None:
        stmt = stmt.where(Hypothesis.proposed_by_run_id == run_id)

    if cursor is not None:
        cursor_at, cursor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Hypothesis.created_at < cursor_at,
                and_(
                    Hypothesis.created_at == cursor_at,
                    Hypothesis.id < cursor_id,
                ),
            )
        )

    stmt = stmt.order_by(
        Hypothesis.created_at.desc(), Hypothesis.id.desc()
    ).limit(limit + 1)

    rows = (await session.execute(stmt)).scalars().all()

    has_more = len(rows) > limit
    page_rows = list(rows[:limit])
    next_cursor: str | None = None
    if has_more and page_rows:
        last = page_rows[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)

    return HypothesisListResponse(
        items=[_to_public(row) for row in page_rows],
        next_cursor=next_cursor,
    )


@router.get(
    "/hypotheses/{hypothesis_id}",
    response_model=HypothesisPublic,
)
async def get_hypothesis(
    hypothesis_id: uuid.UUID, session: SessionDep
) -> HypothesisPublic:
    row = await _load_hypothesis(session=session, hypothesis_id=hypothesis_id)
    return _to_public(row)


@router.get(
    "/hypotheses/{hypothesis_id}/belief",
    response_model=HypothesisBeliefResponse,
)
async def get_hypothesis_belief(
    hypothesis_id: uuid.UUID, session: SessionDep
) -> HypothesisBeliefResponse:
    row = await _load_hypothesis(session=session, hypothesis_id=hypothesis_id)
    latest = (
        await session.execute(
            select(BeliefRecomputation)
            .where(BeliefRecomputation.hypothesis_id == hypothesis_id)
            .order_by(
                BeliefRecomputation.computed_at.desc(),
                BeliefRecomputation.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return HypothesisBeliefResponse(
        hypothesis=_to_public(row),
        latest=_to_belief_public(latest) if latest is not None else None,
    )


@router.get(
    "/hypotheses/{hypothesis_id}/belief/history",
    response_model=HypothesisHistoryResponse,
)
async def get_hypothesis_belief_history(
    hypothesis_id: uuid.UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> HypothesisHistoryResponse:
    await _load_hypothesis(session=session, hypothesis_id=hypothesis_id)
    rows = (
        (
            await session.execute(
                select(BeliefRecomputation)
                .where(BeliefRecomputation.hypothesis_id == hypothesis_id)
                .order_by(
                    BeliefRecomputation.computed_at.desc(),
                    BeliefRecomputation.id.desc(),
                )
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return HypothesisHistoryResponse(
        items=[_to_belief_public(row) for row in rows]
    )


@router.get(
    "/hypotheses/{hypothesis_id}/lifecycle",
    response_model=HypothesisLifecycleResponse,
)
async def get_hypothesis_lifecycle(
    hypothesis_id: uuid.UUID, session: SessionDep
) -> HypothesisLifecycleResponse:
    row = await _load_hypothesis(session=session, hypothesis_id=hypothesis_id)

    parent = await _load_optional(
        session=session, hypothesis_id=row.parent_hypothesis_id
    )
    superseded_by = await _load_optional(
        session=session, hypothesis_id=row.superseded_by_id
    )
    supersedes = await _load_supersedes(session=session, hypothesis_id=row.id)

    children_rows = (
        (
            await session.execute(
                select(Hypothesis)
                .where(Hypothesis.parent_hypothesis_id == row.id)
                .order_by(
                    Hypothesis.created_at.desc(), Hypothesis.id.desc()
                )
            )
        )
        .scalars()
        .all()
    )

    conditional_edges = await _load_conditional_edges(
        session=session, hypothesis_entity_id=row.entity_id
    )

    recent_resolutions: list[EventResolutionPublic] = []
    if conditional_edges:
        event_entity_ids = {edge.event_entity_id for edge in conditional_edges}
        resolution_rows = (
            (
                await session.execute(
                    select(EventResolution)
                    .where(EventResolution.event_entity_id.in_(event_entity_ids))
                    .order_by(
                        EventResolution.resolved_at.desc(),
                        EventResolution.id.desc(),
                    )
                    .limit(_RECENT_RESOLUTIONS_LIMIT)
                )
            )
            .scalars()
            .all()
        )
        recent_resolutions = [
            EventResolutionPublic.model_validate(item) for item in resolution_rows
        ]

    return HypothesisLifecycleResponse(
        hypothesis=_to_public(row),
        parent=_to_public(parent) if parent is not None else None,
        children=[_to_public(child) for child in children_rows],
        supersedes=_to_public(supersedes) if supersedes is not None else None,
        superseded_by=_to_public(superseded_by) if superseded_by is not None else None,
        conditional_edges=conditional_edges,
        recent_event_resolutions=recent_resolutions,
    )


@router.post(
    "/hypotheses/{hypothesis_id}/activate",
    response_model=HypothesisPublic,
)
async def activate_hypothesis(
    hypothesis_id: uuid.UUID, session: SessionDep
) -> HypothesisPublic:
    row = await _load_hypothesis(session=session, hypothesis_id=hypothesis_id)
    if row.status != HypothesisStatus.proposed.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"hypothesis is in state {row.status!r}, only 'proposed' can be activated"
            ),
        )
    row.status = HypothesisStatus.active.value
    row.last_activity_at = datetime.now(UTC)
    if row.proposed_by_run_id is not None:
        await _emit_activation_event(
            session=session,
            run_id=row.proposed_by_run_id,
            hypothesis_id=row.id,
        )
    await session.commit()
    await session.refresh(row)
    return _to_public(row)


@router.post(
    "/hypotheses/{hypothesis_id}/transition",
    response_model=HypothesisPublic,
)
async def transition_hypothesis(
    hypothesis_id: uuid.UUID,
    payload: HypothesisTransitionRequest,
    session: SessionDep,
) -> HypothesisPublic:
    """Manually transition a hypothesis to one of the allowed next states.

    Allowed transitions:
    - `proposed → active | expired | superseded`
    - `active   → validated | falsified | expired | superseded`

    Any other source state (including terminal `validated` / `falsified` /
    `expired` / `superseded`) returns 409.
    """
    row = await _load_hypothesis(session=session, hypothesis_id=hypothesis_id)
    target = payload.to.value
    allowed = _ALLOWED_TRANSITIONS.get(row.status)
    if allowed is None or target not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"transition from {row.status!r} to {target!r} is not allowed"
            ),
        )
    previous = row.status
    row.status = target
    effective_now = datetime.now(UTC)
    row.last_activity_at = effective_now
    if target in {
        HypothesisStatus.expired.value,
        HypothesisStatus.superseded.value,
    }:
        row.archived_at = effective_now
        row.archived_reason = payload.reason or target
    if row.proposed_by_run_id is not None:
        emit_run_event(
            session,
            run_id=row.proposed_by_run_id,
            level=RunEventLevel.info,
            message=(
                f"hypothesis {row.id} transitioned {previous} → {target}"
            ),
            data={
                "event": _HYPOTHESIS_TRANSITIONED_EVENT,
                "hypothesis_id": str(row.id),
                "from": previous,
                "to": target,
                "reason": payload.reason,
            },
        )
    await session.commit()
    await session.refresh(row)
    return _to_public(row)


_NON_TERMINAL_PARENT_STATUSES: Final[frozenset[str]] = frozenset(
    {HypothesisStatus.proposed.value, HypothesisStatus.active.value}
)


@router.post(
    "/hypotheses/{hypothesis_id}/parent",
    response_model=HypothesisPublic,
)
async def set_hypothesis_parent(
    hypothesis_id: uuid.UUID,
    payload: HypothesisParentRequest,
    session: SessionDep,
) -> HypothesisPublic:
    """Set or clear `parent_hypothesis_id` on a hypothesis.

    Pass `{"parent_id": null}` to clear. Returns 404 if either the child or
    the parent is missing; 409 if the parent is in a terminal state or the
    child would become its own parent.
    """
    row = await _load_hypothesis(session=session, hypothesis_id=hypothesis_id)
    if payload.parent_id is None:
        row.parent_hypothesis_id = None
        await session.commit()
        await session.refresh(row)
        return _to_public(row)
    if payload.parent_id == hypothesis_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="hypothesis cannot be its own parent",
        )
    parent = (
        await session.execute(
            select(Hypothesis).where(Hypothesis.id == payload.parent_id)
        )
    ).scalar_one_or_none()
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"parent hypothesis {payload.parent_id} not found",
        )
    if parent.status not in _NON_TERMINAL_PARENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"parent hypothesis {payload.parent_id} is in terminal state "
                f"{parent.status!r}"
            ),
        )
    row.parent_hypothesis_id = parent.id
    await session.commit()
    await session.refresh(row)
    return _to_public(row)


@router.post(
    "/hypotheses/lifecycle/sweep",
    response_model=LifecycleSweepResponse,
)
async def sweep_lifecycle(session: SessionDep) -> LifecycleSweepResponse:
    report = await run_lifecycle_sweep(session=session)
    await session.commit()
    return LifecycleSweepResponse(
        counts=LifecycleSweepCounts(
            expired=len(report.expired_ids),
            archived_belief_floor=len(report.archived_belief_floor_ids),
            validated=len(report.validated_ids),
            falsified=len(report.falsified_ids),
            stagnation_flagged=len(report.stagnation_flagged_ids),
        ),
        expired_ids=list(report.expired_ids),
        archived_belief_floor_ids=list(report.archived_belief_floor_ids),
        validated_ids=list(report.validated_ids),
        falsified_ids=list(report.falsified_ids),
        stagnation_flagged_ids=list(report.stagnation_flagged_ids),
    )


async def _load_hypothesis(
    *, session: AsyncSession, hypothesis_id: uuid.UUID
) -> Hypothesis:
    row = (
        await session.execute(
            select(Hypothesis).where(Hypothesis.id == hypothesis_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="hypothesis not found"
        )
    return row


async def _load_optional(
    *, session: AsyncSession, hypothesis_id: uuid.UUID | None
) -> Hypothesis | None:
    if hypothesis_id is None:
        return None
    return (
        await session.execute(
            select(Hypothesis).where(Hypothesis.id == hypothesis_id)
        )
    ).scalar_one_or_none()


async def _load_supersedes(
    *, session: AsyncSession, hypothesis_id: uuid.UUID
) -> Hypothesis | None:
    """Find the predecessor that *this* hypothesis superseded, if any.

    The successor (the one inserted by the dedup pipeline) carries no link
    back to the predecessor; the predecessor carries `superseded_by_id`
    pointing at the successor. Walk that backward.
    """
    return (
        await session.execute(
            select(Hypothesis).where(Hypothesis.superseded_by_id == hypothesis_id)
        )
    ).scalar_one_or_none()


async def _load_conditional_edges(
    *, session: AsyncSession, hypothesis_entity_id: uuid.UUID | None
) -> list[ConditionalEdgePublic]:
    if hypothesis_entity_id is None:
        return []
    stmt = (
        select(Relation, Entity)
        .outerjoin(Entity, Relation.from_id == Entity.id)
        .where(
            Relation.to_id == hypothesis_entity_id,
            Relation.type.in_(_CONDITIONAL_RELATION_TYPES),
        )
        .order_by(Relation.created_at.asc(), Relation.id.asc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        ConditionalEdgePublic(
            relation_id=relation.id,
            relation_type=relation.type,
            event_entity_id=relation.from_id,
            event_entity_name=event.canonical_name if event is not None else None,
        )
        for relation, event in rows
    ]


def _to_belief_public(row: BeliefRecomputation) -> BeliefRecomputationPublic:
    inputs = (
        [BeliefInputBreakdown.model_validate(item) for item in row.inputs]
        if row.inputs is not None
        else None
    )
    return BeliefRecomputationPublic(
        id=row.id,
        hypothesis_id=row.hypothesis_id,
        computed_at=row.computed_at,
        belief=row.belief,
        contributing_evidence_ids=list(row.contributing_evidence_ids or []),
        computation_method=row.computation_method,
        inputs=inputs,
    )


async def _emit_activation_event(
    *, session: AsyncSession, run_id: uuid.UUID, hypothesis_id: uuid.UUID
) -> None:
    emit_run_event(
        session,
        run_id=run_id,
        level=RunEventLevel.info,
        message=f"hypothesis {hypothesis_id} activated",
        data={
            "event": _HYPOTHESIS_ACTIVATED_EVENT,
            "hypothesis_id": str(hypothesis_id),
        },
    )


__all__ = ["router"]
