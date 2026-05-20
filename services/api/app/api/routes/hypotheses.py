import base64
import binascii
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.db.models_graph import BeliefRecomputation, Hypothesis, HypothesisStatus
from app.db.models_runs import RunEventLevel
from app.schemas.graph import (
    BeliefInputBreakdown,
    BeliefRecomputationPublic,
)
from app.schemas.hypotheses import (
    HypothesisBeliefResponse,
    HypothesisHistoryResponse,
    HypothesisListResponse,
    HypothesisPublic,
    HypothesisState,
    HypothesisStateFilter,
)
from app.services.run_events import emit_run_event

router = APIRouter()

_HYPOTHESIS_ACTIVATED_EVENT = "hypothesis_activated"


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
    if row.proposed_by_run_id is not None:
        await _emit_activation_event(
            session=session,
            run_id=row.proposed_by_run_id,
            hypothesis_id=row.id,
        )
    await session.commit()
    await session.refresh(row)
    return _to_public(row)


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
