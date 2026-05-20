"""Persist a `SectorBrief` row into `sector_briefs`.

Writes the typed payload, verifier status, regeneration count, judge fields,
and wall-clock measurement. Does NOT mark the parent run as succeeded — the
parent orchestrator does that after the consolidate stage.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_sector import SectorBrief as SectorBriefRow
from app.schemas.sector_brief import JudgePublic, SectorBrief
from app.services.evals.gate_runner import run_gate_for_sector_brief


async def persist_sector_brief(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    brief: SectorBrief,
    judge: JudgePublic,
    wall_clock_ms: int,
) -> uuid.UUID:
    row = SectorBriefRow(
        run_id=run_id,
        sector_entity_id=brief.sector_entity_id,
        direction=brief.direction.value,
        payload=brief.model_dump(mode="json"),
        verifier_status=brief.verifier_status.value,
        regeneration_count=brief.regeneration_count,
        judge_status=judge.status.value,
        judge_reasons=list(judge.reasons) if judge.reasons else None,
        judge_call_id=judge.call_id,
        wall_clock_ms=wall_clock_ms,
    )
    session.add(row)
    await session.flush()
    await run_gate_for_sector_brief(
        session=session,
        run_id=run_id,
        brief_id=row.id,
        brief=brief,
    )
    return row.id


__all__ = ["persist_sector_brief"]
