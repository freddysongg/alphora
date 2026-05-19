"""Stage 4 portfolio brief orchestrator.

Loads persisted sector briefs and company theses for a run, calls the
deterministic aggregator with the in-scope macro brief and judge, runs the
LLM judge as advisory (no regeneration), and persists a single
`portfolio_briefs` row keyed to the run.

The judge is best-effort: any failure downgrades to `status='not_run'` and
emits a warn event; budget pause/kill is routed through the orchestrator
and re-raised as `FunnelResearchError` so the parent's halt-on-paused
logic engages.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_company import CompanyThesis as CompanyThesisRow
from app.db.models_graph import Evidence, EvidenceChunk
from app.db.models_portfolio import PortfolioBrief as PortfolioBriefRow
from app.db.models_runs import RunEventLevel
from app.db.models_sector import SectorBrief as SectorBriefRow
from app.schemas.company_thesis import CompanyThesis, CompanyThesisPublic
from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import MacroBrief
from app.schemas.portfolio_brief import PortfolioBrief
from app.schemas.sector_brief import (
    JudgePublic,
    JudgeStatus,
    SectorBrief,
    SectorBriefPublic,
)
from app.services.llm.client import LlmClient
from app.services.run_events import emit_run_event
from app.services.run_orchestrator import RunOrchestrator
from app.services.strategies.funnel_research._judge import run_judge
from app.services.strategies.funnel_research.portfolio.aggregator import (
    aggregate_portfolio,
)
from app.services.strategies.funnel_research.portfolio.persist import (
    persist_portfolio_brief,
)


@dataclass(frozen=True)
class PortfolioBriefOutcome:
    persisted: bool
    judge_status: JudgeStatus
    wall_clock_ms: int


async def _load_persisted_sector_briefs(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
) -> list[SectorBriefPublic]:
    rows = (
        (
            await session.execute(
                select(SectorBriefRow)
                .where(SectorBriefRow.run_id == run_id)
                .order_by(SectorBriefRow.created_at)
            )
        )
        .scalars()
        .all()
    )
    briefs: list[SectorBriefPublic] = []
    for row in rows:
        brief = SectorBrief.model_validate(row.payload)
        judge = JudgePublic(
            status=JudgeStatus(row.judge_status),
            reasons=list(row.judge_reasons or []),
            call_id=row.judge_call_id,
        )
        briefs.append(SectorBriefPublic(brief=brief, judge=judge))
    return briefs


async def _load_persisted_company_theses(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
) -> list[CompanyThesisPublic]:
    rows = (
        (
            await session.execute(
                select(CompanyThesisRow)
                .where(CompanyThesisRow.run_id == run_id)
                .order_by(CompanyThesisRow.created_at)
            )
        )
        .scalars()
        .all()
    )
    theses: list[CompanyThesisPublic] = []
    for row in rows:
        thesis = CompanyThesis.model_validate(row.payload)
        judge = JudgePublic(
            status=JudgeStatus(row.judge_status),
            reasons=list(row.judge_reasons or []),
            call_id=row.judge_call_id,
        )
        theses.append(CompanyThesisPublic(thesis=thesis, judge=judge))
    return theses


async def _load_judge_chunks(
    *,
    session: AsyncSession,
    chunk_ids: list[uuid.UUID],
) -> list[EvidenceChunkRef]:
    if not chunk_ids:
        return []
    rows = (
        await session.execute(
            select(EvidenceChunk, Evidence.source)
            .join(Evidence, Evidence.id == EvidenceChunk.evidence_id)
            .where(EvidenceChunk.id.in_(chunk_ids))
        )
    ).all()
    refs: list[EvidenceChunkRef] = []
    for chunk_row, source in rows:
        attributes = dict(chunk_row.attributes or {})
        attributes.setdefault("source", source)
        refs.append(
            EvidenceChunkRef(
                chunk_id=chunk_row.id,
                evidence_id=chunk_row.evidence_id,
                chunk_index=chunk_row.chunk_index,
                text=chunk_row.text,
                attributes=attributes,
            )
        )
    return refs


async def run_portfolio_brief(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    macro_brief: MacroBrief,
    macro_judge: JudgePublic,
    llm_client: LlmClient,
    orchestrator: RunOrchestrator,
) -> PortfolioBriefOutcome:
    started = time.monotonic()
    async with session_factory() as session:
        existing = (
            await session.execute(
                select(PortfolioBriefRow).where(PortfolioBriefRow.run_id == run_id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            emit_run_event(
                session,
                run_id=run_id,
                level=RunEventLevel.info,
                message="portfolio brief resumed from persisted row",
                data={"event": "portfolio_brief_resumed"},
            )
            await session.commit()
            return PortfolioBriefOutcome(
                persisted=True,
                judge_status=JudgeStatus(existing.judge_status),
                wall_clock_ms=existing.wall_clock_ms,
            )
        sectors = await _load_persisted_sector_briefs(session=session, run_id=run_id)
        companies = await _load_persisted_company_theses(
            session=session, run_id=run_id
        )

    brief: PortfolioBrief = aggregate_portfolio(
        run_id=run_id,
        macro=macro_brief,
        macro_judge=macro_judge,
        sectors=sectors,
        companies=companies,
    )

    async with session_factory() as session:
        chunks = await _load_judge_chunks(
            session=session, chunk_ids=list(brief.cited_chunk_ids)
        )
        judge_outcome = await run_judge(
            session=session,
            run_id=run_id,
            brief=brief,
            brief_kind="portfolio",
            chunks=chunks,
            llm_complete=llm_client.complete,
            orchestrator_pause=orchestrator.pause,
            orchestrator_fail=orchestrator.fail,
        )
        wall_clock_ms = int((time.monotonic() - started) * 1000)
        await persist_portfolio_brief(
            session=session,
            run_id=run_id,
            brief=brief,
            judge=judge_outcome.public,
            wall_clock_ms=wall_clock_ms,
        )
        await session.commit()

    return PortfolioBriefOutcome(
        persisted=True,
        judge_status=judge_outcome.public.status,
        wall_clock_ms=wall_clock_ms,
    )


__all__ = ["PortfolioBriefOutcome", "run_portfolio_brief"]
