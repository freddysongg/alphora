import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from app.api.deps import OrchestratorDep, QueueDep, SessionDep
from app.api.sse import format_sse_event
from app.db.models_runs import (
    ResearchRun,
    RunEvent,
    RunStatus,
)
from app.db.session import session_factory
from app.schemas.runs import (
    CreateResearchRunsRequest,
    GroupedRuns,
    ResearchRunDetail,
    ResearchRunSummary,
)
from app.services.run_orchestrator import RunOrchestratorError

router = APIRouter()

_TERMINAL_STATUSES: frozenset[RunStatus] = frozenset(
    {RunStatus.succeeded, RunStatus.failed, RunStatus.cancelled}
)
_SSE_POLL_INTERVAL_SECONDS: float = 1.0
_SSE_EVENT_BATCH_LIMIT: int = 100
_GROUPED_RECENT_WINDOW_DAYS: int = 7
_GROUPED_RECENT_LIMIT: int = 50
_DETAIL_EVENT_LIMIT: int = 200


def _build_run_config(request: CreateResearchRunsRequest) -> dict[str, object]:
    return {
        "analysts": [a.value for a in request.analysts],
        "llm_provider": request.llm_provider.value,
        "llm_model": request.llm_model,
        "debate_depth": request.debate_depth,
    }


@router.post(
    "",
    response_model=list[ResearchRunSummary],
    status_code=status.HTTP_201_CREATED,
)
async def create_research_runs(
    payload: CreateResearchRunsRequest,
    session: SessionDep,
    queue: QueueDep,
) -> list[ResearchRunSummary]:
    config = _build_run_config(payload)
    created: list[ResearchRun] = []
    for ticker in payload.tickers:
        run = ResearchRun(
            id=uuid.uuid4(),
            ticker=ticker,
            trade_date=payload.trade_date,
            status=RunStatus.queued,
            config=config,
        )
        session.add(run)
        created.append(run)
    await session.commit()
    for run in created:
        queue.enqueue("app.workers.tasks.execute_research_run", run.id.hex)
    return [ResearchRunSummary.model_validate(run) for run in created]


def _to_status_enum(value: str) -> RunStatus:
    try:
        return RunStatus(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid status filter: {value}",
        ) from exc


@router.get("", response_model=list[ResearchRunSummary] | GroupedRuns)
async def list_research_runs(
    session: SessionDep,
    status_filter: Annotated[list[str] | None, Query(alias="status")] = None,
    ticker: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    group: Annotated[str | None, Query()] = None,
) -> list[ResearchRunSummary] | GroupedRuns:
    if group == "status":
        return await _grouped_runs(session)
    stmt = select(ResearchRun).order_by(desc(ResearchRun.created_at))
    if status_filter:
        statuses = [_to_status_enum(value) for value in status_filter]
        stmt = stmt.where(ResearchRun.status.in_(statuses))
    if ticker:
        stmt = stmt.where(ResearchRun.ticker == ticker.upper())
    stmt = stmt.limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [ResearchRunSummary.model_validate(row) for row in rows]


async def _grouped_runs(session: SessionDep) -> GroupedRuns:
    queued_stmt = (
        select(ResearchRun)
        .where(ResearchRun.status == RunStatus.queued)
        .order_by(desc(ResearchRun.created_at))
    )
    running_stmt = (
        select(ResearchRun)
        .where(ResearchRun.status == RunStatus.running)
        .order_by(desc(ResearchRun.created_at))
    )
    failed_stmt = (
        select(ResearchRun)
        .where(ResearchRun.status == RunStatus.failed)
        .order_by(desc(ResearchRun.created_at))
    )
    recent_cutoff = datetime.now(UTC) - timedelta(days=_GROUPED_RECENT_WINDOW_DAYS)
    recent_stmt = (
        select(ResearchRun)
        .where(ResearchRun.status == RunStatus.succeeded)
        .where(ResearchRun.created_at >= recent_cutoff)
        .order_by(desc(ResearchRun.created_at))
        .limit(_GROUPED_RECENT_LIMIT)
    )
    queued_rows = (await session.execute(queued_stmt)).scalars().all()
    running_rows = (await session.execute(running_stmt)).scalars().all()
    failed_rows = (await session.execute(failed_stmt)).scalars().all()
    recent_rows = (await session.execute(recent_stmt)).scalars().all()
    return GroupedRuns(
        queued=[ResearchRunSummary.model_validate(r) for r in queued_rows],
        running=[ResearchRunSummary.model_validate(r) for r in running_rows],
        recent=[ResearchRunSummary.model_validate(r) for r in recent_rows],
        failed=[ResearchRunSummary.model_validate(r) for r in failed_rows],
    )


@router.get("/{run_id}", response_model=ResearchRunDetail)
async def get_research_run(run_id: uuid.UUID, session: SessionDep) -> ResearchRunDetail:
    stmt = (
        select(ResearchRun)
        .where(ResearchRun.id == run_id)
        .options(
            selectinload(ResearchRun.reports),
            selectinload(ResearchRun.provenance),
        )
    )
    run = (await session.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="research run not found")
    events_stmt = (
        select(RunEvent)
        .where(RunEvent.run_id == run_id)
        .order_by(desc(RunEvent.at))
        .limit(_DETAIL_EVENT_LIMIT)
    )
    event_rows = (await session.execute(events_stmt)).scalars().all()
    return ResearchRunDetail.model_validate(
        {
            "id": run.id,
            "ticker": run.ticker,
            "trade_date": run.trade_date,
            "status": run.status,
            "config": run.config,
            "final_rating": run.final_rating,
            "final_decision_summary": run.final_decision_summary,
            "wall_clock_ms": run.wall_clock_ms,
            "error_message": run.error_message,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "reports": run.reports,
            "events": list(reversed(event_rows)),
            "provenance": run.provenance,
        }
    )


async def _stream_run_events(run_id: uuid.UUID) -> AsyncIterator[str]:
    last_event_at: datetime | None = None
    seen_event_ids: set[uuid.UUID] = set()
    try:
        while True:
            terminal_status: RunStatus | None = None
            new_events: list[RunEvent] = []
            async with session_factory() as session:
                run = (
                    await session.execute(
                        select(ResearchRun).where(ResearchRun.id == run_id)
                    )
                ).scalar_one_or_none()
                if run is None:
                    yield format_sse_event(
                        event="error", data={"detail": "research run not found"}
                    )
                    return
                events_stmt = select(RunEvent).where(RunEvent.run_id == run_id)
                if last_event_at is not None:
                    events_stmt = events_stmt.where(RunEvent.at >= last_event_at)
                events_stmt = events_stmt.order_by(RunEvent.at).limit(_SSE_EVENT_BATCH_LIMIT)
                new_events = list((await session.execute(events_stmt)).scalars().all())
                if run.status in _TERMINAL_STATUSES:
                    terminal_status = run.status
            for event in new_events:
                if event.id in seen_event_ids:
                    continue
                seen_event_ids.add(event.id)
                last_event_at = event.at
                yield format_sse_event(
                    event="log",
                    data={
                        "id": str(event.id),
                        "at": event.at.isoformat(),
                        "level": event.level.value,
                        "message": event.message,
                    },
                )
            if terminal_status is not None:
                yield format_sse_event(event="end", data={"status": terminal_status.value})
                return
            await asyncio.sleep(_SSE_POLL_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        return


@router.get("/{run_id}/events")
async def stream_research_run_events(run_id: uuid.UUID) -> StreamingResponse:
    return StreamingResponse(
        _stream_run_events(run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{run_id}/cancel", response_model=ResearchRunSummary)
async def cancel_research_run(
    run_id: uuid.UUID,
    session: SessionDep,
    orchestrator: OrchestratorDep,
) -> ResearchRunSummary:
    existing = (
        await session.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    ).scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="research run not found")
    if existing.status in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"run already terminal: {existing.status.value}",
        )
    try:
        await orchestrator.cancel(run_id)
    except RunOrchestratorError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    await session.refresh(existing)
    return ResearchRunSummary.model_validate(existing)


__all__ = ["router"]
