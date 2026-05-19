import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_runs import ResearchRun, RunStatus
from app.schemas.macro_brief import MacroBrief
from app.services.run_events import emit_stage_event
from app.services.run_orchestrator import resolve_stage_position


async def persist_macro_brief(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    brief: MacroBrief,
    wall_clock_ms: int,
    mark_succeeded: bool = True,
) -> uuid.UUID:
    """Persist a `MacroBrief` row. By default also marks the run succeeded.

    Pass `mark_succeeded=False` when the caller has more stages to run
    (sector fan-out + consolidate) and will mark the run succeeded itself.
    """
    row = MacroBriefRow(
        run_id=run_id,
        themes=[t.model_dump(mode="json") for t in brief.themes],
        sector_calls=[c.model_dump(mode="json") for c in brief.sector_calls],
        watch_items=[w.model_dump(mode="json") for w in brief.watch_items],
        cited_claims=[c.model_dump(mode="json") for c in brief.cited_claims],
        proposed_hypotheses=[p.model_dump(mode="json") for p in brief.proposed_hypotheses],
        confidence=brief.confidence,
        verifier_status=brief.verifier_status.value,
        regeneration_count=brief.regeneration_count,
        evidence_ids=[str(eid) for eid in brief.evidence_ids],
    )
    session.add(row)
    await session.flush()

    if not mark_succeeded:
        return row.id

    run = (await session.execute(select(ResearchRun).where(ResearchRun.id == run_id))).scalar_one()
    if run.status == RunStatus.running:
        run.status = RunStatus.succeeded
        run.finished_at = datetime.now(UTC)
        run.wall_clock_ms = wall_clock_ms

        index, total = resolve_stage_position(strategy=run.strategy, stage_name="succeeded")
        emit_stage_event(
            session,
            run_id=run_id,
            stage_name="succeeded",
            stage_index=index,
            total_stages=total,
        )
    return row.id


async def mark_run_succeeded(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    wall_clock_ms: int,
) -> None:
    """Mark the run as succeeded and emit the terminal `succeeded` stage event."""
    run = (
        await session.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    ).scalar_one()
    if run.status != RunStatus.running:
        return
    run.status = RunStatus.succeeded
    run.finished_at = datetime.now(UTC)
    run.wall_clock_ms = wall_clock_ms
    index, total = resolve_stage_position(strategy=run.strategy, stage_name="succeeded")
    emit_stage_event(
        session,
        run_id=run_id,
        stage_name="succeeded",
        stage_index=index,
        total_stages=total,
    )


__all__ = ["mark_run_succeeded", "persist_macro_brief"]
