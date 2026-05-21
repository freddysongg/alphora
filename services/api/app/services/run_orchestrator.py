from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_runs import ResearchRun, RunEventLevel, RunStatus
from app.services.run_events import (
    PAUSE_EVENT,
    RESUME_EVENT,
    emit_run_event,
    emit_stage_event,
)

StageScheme = tuple[str, ...]

STAGE_SCHEMES: dict[str, StageScheme] = {
    "funnel_research": (
        "ingest",
        "digest",
        "synthesize",
        "verify",
        "sector_fanout",
        "company_fanout",
        "portfolio_brief",
        "belief_update",
        "consolidate",
    ),
}

_TERMINAL_STAGE_NAMES: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})


class RunOrchestratorError(Exception):
    """Raised when orchestrator preconditions fail (e.g. run not found)."""


def resolve_stage_position(*, strategy: str, stage_name: str) -> tuple[int, int]:
    scheme = STAGE_SCHEMES.get(strategy)
    if scheme is None:
        raise RunOrchestratorError(f"unknown strategy {strategy!r}")
    total = len(scheme) + 1
    if stage_name in _TERMINAL_STAGE_NAMES:
        return total, total
    try:
        index = scheme.index(stage_name) + 1
    except ValueError as exc:
        raise RunOrchestratorError(
            f"unknown stage {stage_name!r} for strategy {strategy!r}"
        ) from exc
    return index, total


def _emit_strategy_stage(
    session: AsyncSession,
    *,
    run_id: UUID,
    strategy: str,
    stage_name: str,
    message: str | None = None,
    level: RunEventLevel = RunEventLevel.info,
) -> None:
    index, total = resolve_stage_position(strategy=strategy, stage_name=stage_name)
    emit_stage_event(
        session,
        run_id=run_id,
        stage_name=stage_name,
        stage_index=index,
        total_stages=total,
        message=message,
        level=level,
    )


class RunOrchestrator:
    """Coordinates the lifecycle of a research run.

    The orchestrator owns status transitions (queued → running → terminal) and
    emits per-stage events. Strategy execution lives outside this class; the
    worker dispatches into the strategy's runner directly.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def start(self, run_id: UUID) -> None:
        async with self._session_factory() as session:
            run = await self._load_run(session, run_id)
            if run.status != RunStatus.queued:
                return
            run.status = RunStatus.running
            run.started_at = _utcnow()
            await session.commit()

    async def fail(self, run_id: UUID, reason: str) -> None:
        """Mark a queued or running run as failed with the given reason.

        Used when the worker rejects a run at dispatch (e.g., unimplemented
        strategy) or when a strategy runner surfaces a terminal failure. When
        the run's strategy is unknown to `STAGE_SCHEMES` we still mark the row
        failed and emit a plain run event — failing to look up a stage position
        must never block the status transition.
        """
        async with self._session_factory() as session:
            run = await self._load_run(session, run_id)
            if run.status not in {RunStatus.queued, RunStatus.running}:
                return
            run.status = RunStatus.failed
            run.error_message = reason
            run.finished_at = _utcnow()
            try:
                _emit_strategy_stage(
                    session,
                    run_id=run_id,
                    strategy=run.strategy,
                    stage_name="failed",
                    message=f"run failed: {reason}",
                    level=RunEventLevel.err,
                )
            except RunOrchestratorError:
                emit_run_event(
                    session,
                    run_id=run_id,
                    level=RunEventLevel.err,
                    message=f"run failed: {reason}",
                    data={"event": "run_failed", "reason": reason},
                )
            await session.commit()

    async def cancel(self, run_id: UUID) -> None:
        async with self._session_factory() as session:
            run = await self._load_run(session, run_id)
            if run.status not in {RunStatus.queued, RunStatus.running, RunStatus.paused}:
                return
            run.status = RunStatus.cancelled
            run.finished_at = _utcnow()
            try:
                _emit_strategy_stage(
                    session,
                    run_id=run_id,
                    strategy=run.strategy,
                    stage_name="cancelled",
                    level=RunEventLevel.warn,
                )
            except RunOrchestratorError:
                emit_run_event(
                    session,
                    run_id=run_id,
                    level=RunEventLevel.warn,
                    message="run cancelled",
                    data={"event": "run_cancelled"},
                )
            await session.commit()

    async def pause(self, run_id: UUID, reason: str) -> None:
        async with self._session_factory() as session:
            run = await self._load_run(session, run_id)
            if run.status == RunStatus.paused:
                return
            if run.status != RunStatus.running:
                raise RunOrchestratorError(
                    f"cannot pause run {run_id} from status {run.status.value}"
                )
            run.status = RunStatus.paused
            run.finished_at = None
            emit_run_event(
                session,
                run_id=run_id,
                level=RunEventLevel.warn,
                message=f"run paused: {reason}",
                data={"event": PAUSE_EVENT, "reason": reason},
            )
            await session.commit()

    async def resume(self, run_id: UUID) -> None:
        async with self._session_factory() as session:
            run = await self._load_run(session, run_id)
            if run.status in {RunStatus.queued, RunStatus.running}:
                return
            if run.status != RunStatus.paused:
                raise RunOrchestratorError(
                    f"cannot resume run {run_id} from status {run.status.value}"
                )
            run.status = RunStatus.queued
            emit_run_event(
                session,
                run_id=run_id,
                level=RunEventLevel.info,
                message="run resumed",
                data={"event": RESUME_EVENT},
            )
            await session.commit()

    async def _load_run(self, session: AsyncSession, run_id: UUID) -> ResearchRun:
        stmt = select(ResearchRun).where(ResearchRun.id == run_id)
        result = await session.execute(stmt)
        run = result.scalar_one_or_none()
        if run is None:
            raise RunOrchestratorError(f"research run {run_id} not found")
        return run


def _utcnow() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "STAGE_SCHEMES",
    "RunOrchestrator",
    "RunOrchestratorError",
    "resolve_stage_position",
]
