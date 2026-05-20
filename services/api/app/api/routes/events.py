"""Event-resolution ingestion (Phase 4).

A single endpoint that persists an `EventResolution` row for a known event
entity and immediately fans out to bound hypotheses via the conditional
edges (`validates_if_beat` / `falsifies_if_miss`). The endpoint runs in one
transaction so a successful response means both the audit row and the
state transitions on linked hypotheses have committed together.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.db.models_graph import Entity, EntityType, EventResolution
from app.schemas.graph import EventResolutionPublic
from app.schemas.hypotheses import (
    EventResolutionRequest,
    EventResolutionResponse,
)
from app.services.hypothesis import (
    apply_event_resolution,
    record_event_resolution,
)
from app.services.hypothesis.events import InvalidEventResolutionKindError

router = APIRouter()


@router.post(
    "/events/{event_entity_id}/resolve",
    response_model=EventResolutionResponse,
)
async def resolve_event(
    event_entity_id: uuid.UUID,
    payload: EventResolutionRequest,
    session: SessionDep,
) -> EventResolutionResponse:
    """Record an event resolution and apply its effect to bound hypotheses.

    422 when the kind is not one of `beat | miss | neutral`.
    404 when the event entity does not exist or is not an `event` type.
    """
    entity = await _load_event_entity(
        session=session, entity_id=event_entity_id
    )
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"event entity {event_entity_id} not found",
        )

    try:
        resolution = await record_event_resolution(
            session=session,
            event_entity_id=event_entity_id,
            kind=payload.kind,
            resolved_at=payload.resolved_at,
            source_id=payload.source_id,
            notes=payload.notes,
            payload=payload.payload,
        )
    except InvalidEventResolutionKindError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    outcome = await apply_event_resolution(
        session=session, resolution=resolution
    )
    await session.commit()
    await session.refresh(resolution)

    return EventResolutionResponse(
        resolution=EventResolutionPublic.model_validate(resolution),
        validated_hypothesis_ids=list(outcome.validated_hypothesis_ids),
        falsified_hypothesis_ids=list(outcome.falsified_hypothesis_ids),
    )


async def _load_event_entity(
    *, session: AsyncSession, entity_id: uuid.UUID
) -> Entity | None:
    row: Entity | None = (
        await session.execute(select(Entity).where(Entity.id == entity_id))
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.type != EntityType.event.value:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"entity {entity_id} is type {row.type!r}, not 'event'",
        )
    return row


@router.get(
    "/events/{event_entity_id}/resolutions",
    response_model=list[EventResolutionPublic],
)
async def list_event_resolutions(
    event_entity_id: uuid.UUID,
    session: SessionDep,
) -> list[EventResolutionPublic]:
    """Return every resolution recorded against this event entity (newest first)."""
    rows = (
        (
            await session.execute(
                select(EventResolution)
                .where(EventResolution.event_entity_id == event_entity_id)
                .order_by(
                    EventResolution.resolved_at.desc(),
                    EventResolution.id.desc(),
                )
            )
        )
        .scalars()
        .all()
    )
    return [EventResolutionPublic.model_validate(row) for row in rows]


__all__ = ["router"]
