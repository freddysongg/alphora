from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_runs import AnalystKind as DbAnalystKind
from app.db.models_runs import FinalRating as DbFinalRating
from app.db.models_runs import ResearchRun, RunEventLevel, RunReport, RunStatus
from app.services.provenance_recorder import persist_provenance
from app.services.run_events import (
    PAUSE_EVENT,
    RESUME_EVENT,
    emit_run_event,
    emit_stage_event,
)
from app.trading_agents.adapter import TradingAgentsAdapter
from app.trading_agents.types import (
    AnalystKind,
    FinalRating,
    LLMProvider,
    RunConfig,
    RunResult,
)

_ALLOWED_ANALYSTS: frozenset[AnalystKind] = frozenset(
    {"bull", "bear", "macro", "fundamentals", "sentiment", "risk"}
)
_ALLOWED_PROVIDERS: frozenset[LLMProvider] = frozenset({"openai", "anthropic", "together"})

_RUNNING_STAGE_INDEX: int = 1
_TERMINAL_STAGE_INDEX: int = 2
_TOTAL_STAGES: int = 2


class RunOrchestratorError(Exception):
    """Raised when orchestrator preconditions fail (e.g. run not found)."""


class RunOrchestrator:
    """Coordinates the lifecycle of a research run.

    Used by both the API (to enqueue + mark queued) and the worker (to execute).
    All side effects flow through a single async session per phase so failures
    can be persisted independently of the long-running adapter call.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        adapter: TradingAgentsAdapter,
    ) -> None:
        self._session_factory = session_factory
        self._adapter = adapter

    async def start(self, run_id: UUID) -> None:
        async with self._session_factory() as session:
            run = await self._load_run(session, run_id)
            if run.status != RunStatus.queued:
                return
            run.status = RunStatus.running
            run.started_at = _utcnow()
            await session.commit()

    async def execute(self, run_id: UUID) -> None:
        config = await self._mark_running_and_load_config(run_id)
        if config is None:
            return
        try:
            result = self._adapter.run(config)
        except Exception as exc:
            await self._mark_failed(run_id, str(exc))
            return
        await self._persist_success(run_id, result)

    async def cancel(self, run_id: UUID) -> None:
        async with self._session_factory() as session:
            run = await self._load_run(session, run_id)
            if run.status not in {RunStatus.queued, RunStatus.running, RunStatus.paused}:
                return
            run.status = RunStatus.cancelled
            run.finished_at = _utcnow()
            emit_stage_event(
                session,
                run_id=run_id,
                stage_name="cancelled",
                stage_index=_TERMINAL_STAGE_INDEX,
                total_stages=_TOTAL_STAGES,
                level=RunEventLevel.warn,
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

    async def _mark_running_and_load_config(self, run_id: UUID) -> RunConfig | None:
        async with self._session_factory() as session:
            run = await self._load_run(session, run_id)
            if run.status not in {RunStatus.queued, RunStatus.running}:
                return None
            run.status = RunStatus.running
            if run.started_at is None:
                run.started_at = _utcnow()
            emit_stage_event(
                session,
                run_id=run_id,
                stage_name="running",
                stage_index=_RUNNING_STAGE_INDEX,
                total_stages=_TOTAL_STAGES,
                message="execution started",
            )
            await session.commit()
            return _build_run_config(run)

    async def _mark_failed(self, run_id: UUID, message: str) -> None:
        async with self._session_factory() as session:
            run = await self._load_run(session, run_id)
            if run.status != RunStatus.running:
                return
            run.status = RunStatus.failed
            run.error_message = message
            run.finished_at = _utcnow()
            emit_stage_event(
                session,
                run_id=run_id,
                stage_name="failed",
                stage_index=_TERMINAL_STAGE_INDEX,
                total_stages=_TOTAL_STAGES,
                message=f"run failed: {message}",
                level=RunEventLevel.err,
            )
            await session.commit()

    async def _persist_success(self, run_id: UUID, result: RunResult) -> None:
        async with self._session_factory() as session:
            run = await self._load_run(session, run_id)
            if run.status != RunStatus.running:
                return
            run.status = RunStatus.succeeded
            run.final_rating = _map_final_rating(result.final_rating)
            run.final_decision_summary = result.decision_summary
            run.wall_clock_ms = result.wall_clock_ms
            run.finished_at = _utcnow()
            for report in result.reports:
                session.add(
                    RunReport(
                        run_id=run.id,
                        analyst=DbAnalystKind(report.analyst),
                        markdown=report.markdown,
                    )
                )
            persist_provenance(session, run.id, run.ticker, result.provenance)
            emit_stage_event(
                session,
                run_id=run_id,
                stage_name="succeeded",
                stage_index=_TERMINAL_STAGE_INDEX,
                total_stages=_TOTAL_STAGES,
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


def _map_final_rating(rating: FinalRating) -> DbFinalRating:
    if rating == "buy":
        return DbFinalRating.buy
    if rating == "sell":
        return DbFinalRating.sell
    if rating == "hold":
        return DbFinalRating.hold
    return DbFinalRating.none_


def _build_run_config(run: ResearchRun) -> RunConfig:
    config_blob = run.config or {}
    analysts = _parse_analysts(config_blob.get("analysts"))
    llm_provider = _parse_provider(config_blob.get("llm_provider"))
    llm_model = _parse_str(config_blob.get("llm_model"), default="gpt-4o-mini")
    debate_depth = _parse_int(config_blob.get("debate_depth"), default=3)
    return RunConfig(
        ticker=run.ticker,
        trade_date=run.trade_date,
        analysts=analysts,
        llm_provider=llm_provider,
        llm_model=llm_model,
        debate_depth=debate_depth,
    )


def _parse_analysts(value: object) -> list[AnalystKind]:
    if not isinstance(value, list):
        return ["macro", "fundamentals", "sentiment"]
    parsed: list[AnalystKind] = []
    for entry in value:
        if isinstance(entry, str) and entry in _ALLOWED_ANALYSTS:
            kind: AnalystKind = entry
            parsed.append(kind)
    if not parsed:
        return ["macro", "fundamentals", "sentiment"]
    return parsed


def _parse_provider(value: object) -> LLMProvider:
    if isinstance(value, str) and value in _ALLOWED_PROVIDERS:
        provider: LLMProvider = value
        return provider
    return "openai"


def _parse_str(value: object, *, default: str) -> str:
    if isinstance(value, str) and value:
        return value
    return default


def _parse_int(value: object, *, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


__all__ = [
    "RunOrchestrator",
    "RunOrchestratorError",
]
