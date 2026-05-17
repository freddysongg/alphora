from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import RunEvent, RunEventLevel

COST_EVENT: Final[str] = "cost"
STAGE_EVENT: Final[str] = "stage"
PAUSE_EVENT: Final[str] = "pause"
RESUME_EVENT: Final[str] = "resume"


def emit_run_event(
    session: AsyncSession,
    *,
    run_id: UUID,
    level: RunEventLevel,
    message: str,
    data: dict[str, object] | None = None,
) -> RunEvent:
    """Add a RunEvent to the session. Caller flushes/commits.

    Returns the event so callers can read attributes if needed.
    """
    event = RunEvent(
        run_id=run_id,
        level=level,
        message=message,
        data=data,
    )
    session.add(event)
    return event


def emit_stage_event(
    session: AsyncSession,
    *,
    run_id: UUID,
    stage_name: str,
    stage_index: int,
    total_stages: int,
    message: str | None = None,
) -> RunEvent:
    return emit_run_event(
        session,
        run_id=run_id,
        level=RunEventLevel.info,
        message=message or f"stage {stage_index}/{total_stages}: {stage_name}",
        data={
            "event": STAGE_EVENT,
            "stage_name": stage_name,
            "stage_index": stage_index,
            "total_stages": total_stages,
        },
    )


__all__ = [
    "COST_EVENT",
    "PAUSE_EVENT",
    "RESUME_EVENT",
    "STAGE_EVENT",
    "emit_run_event",
    "emit_stage_event",
]
