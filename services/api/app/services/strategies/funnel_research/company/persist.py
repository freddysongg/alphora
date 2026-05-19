"""Persist a `CompanyThesis` row into `company_theses`.

Writes the typed payload, verifier status, regeneration count, judge fields,
and wall-clock measurement. Does NOT mark the parent run as succeeded — the
parent orchestrator does that after the consolidate stage.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_company import CompanyThesis as CompanyThesisRow
from app.schemas.company_thesis import CompanyThesis
from app.schemas.sector_brief import JudgePublic


async def persist_company_thesis(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    thesis: CompanyThesis,
    judge: JudgePublic,
    wall_clock_ms: int,
) -> uuid.UUID:
    row = CompanyThesisRow(
        run_id=run_id,
        company_entity_id=thesis.company_entity_id,
        sector_entity_id=thesis.sector_entity_id,
        ticker=thesis.ticker,
        direction=thesis.direction.value,
        payload=thesis.model_dump(mode="json"),
        verifier_status=thesis.verifier_status.value,
        regeneration_count=thesis.regeneration_count,
        judge_status=judge.status.value,
        judge_reasons=list(judge.reasons) if judge.reasons else None,
        judge_call_id=judge.call_id,
        wall_clock_ms=wall_clock_ms,
    )
    session.add(row)
    await session.flush()
    return row.id


__all__ = ["persist_company_thesis"]
