"""Persist a `PortfolioBrief` row into `portfolio_briefs`.

Writes the serialized payload, verifier status, regeneration count, judge
fields, and wall-clock measurement. One row per run; unique on `run_id`.
The aggregator is deterministic so `verifier_status` is always `verified`
and `regeneration_count` is always `0`.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_portfolio import PortfolioBrief as PortfolioBriefRow
from app.schemas.portfolio_brief import PortfolioBrief
from app.schemas.sector_brief import JudgePublic


async def persist_portfolio_brief(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    brief: PortfolioBrief,
    judge: JudgePublic,
    wall_clock_ms: int,
) -> uuid.UUID:
    row = PortfolioBriefRow(
        run_id=run_id,
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
    return row.id


__all__ = ["persist_portfolio_brief"]
