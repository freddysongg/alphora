"""Stage 2 sector fan-out orchestrator.

Selects the top non-neutral sectors from a verified macro brief, runs the
per-sector pipeline (evidence fetch → extraction → graph persist → synthesis
→ regen → judge → persist) under bounded concurrency, and reports aggregate
counts back to the parent run. The parent orchestrator decides whether to
fail the run based on the outcome (`failed_count == selected_count`).

Per-sector progress is emitted as `info`-level run events on the parent run.
Stage events are not emitted per sector — the UI consumes a single timeline.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_runs import RunEventLevel
from app.db.models_sector import SectorBrief as SectorBriefRow
from app.schemas.macro_brief import MacroBrief, SectorCall, VerifierStatus
from app.schemas.sector_brief import JudgePublic, JudgeStatus, SectorBrief
from app.services.extraction import ExtractionBudgetHaltError
from app.services.llm.client import LlmClient
from app.services.run_events import emit_run_event
from app.services.run_orchestrator import RunOrchestrator
from app.services.strategies.funnel_research._errors import FunnelResearchError
from app.services.strategies.funnel_research._judge import run_judge
from app.services.strategies.funnel_research.sector.evidence import (
    SectorSourceFetcher,
    fetch_sector_evidence,
)
from app.services.strategies.funnel_research.sector.extraction import (
    extract_sector_chunks,
)
from app.services.strategies.funnel_research.sector.graph import (
    persist_sector_candidates,
)
from app.services.strategies.funnel_research.sector.llm_call import (
    call_sector_synthesis,
)
from app.services.strategies.funnel_research.sector.persist import (
    persist_sector_brief,
)
from app.services.strategies.funnel_research.sector.resolve import (
    resolve_sector_company_entity_ids,
)
from app.services.strategies.funnel_research.sector.selector import (
    MAX_SECTOR_DEEP_DIVES,
    select_sectors,
)
from app.services.strategies.funnel_research.sector.verifier import (
    run_sector_regen_loop,
)
from app.services.strategies.funnel_research.sector_constituents import (
    SectorConstituents,
)

SECTOR_FANOUT_CONCURRENCY = 2


class _SectorOutcome(StrEnum):
    persisted = "persisted"
    skipped = "skipped"
    failed = "failed"


@dataclass(frozen=True)
class SectorFanoutOutcome:
    selected_count: int
    persisted_count: int
    skipped_count: int
    failed_count: int


async def run_sector_fanout(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    macro_brief: MacroBrief,
    digest_markdown: str,
    sector_constituents: dict[str, SectorConstituents],
    llm_client: LlmClient,
    orchestrator: RunOrchestrator,
    http_client: httpx.AsyncClient,
    sector_fetcher: SectorSourceFetcher | None = None,
    max_sectors: int = MAX_SECTOR_DEEP_DIVES,
    concurrency: int = SECTOR_FANOUT_CONCURRENCY,
) -> SectorFanoutOutcome:
    """Run sector fan-out for a verified macro brief.

    Returns aggregate counts: selected (≤ max), persisted, skipped (no
    evidence / no constituents), failed (synthesis/extraction error). Parent
    decides whether to fail the run based on the counts.
    """
    selected = select_sectors(macro_brief, max_count=max_sectors)
    if not selected:
        return SectorFanoutOutcome(
            selected_count=0, persisted_count=0, skipped_count=0, failed_count=0
        )

    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        asyncio.create_task(
            _run_one_sector(
                session_factory=session_factory,
                run_id=run_id,
                macro_brief=macro_brief,
                sector_call=call,
                constituents=sector_constituents.get(call.sector_name),
                digest_markdown=digest_markdown,
                llm_client=llm_client,
                orchestrator=orchestrator,
                http_client=http_client,
                sector_fetcher=sector_fetcher,
                semaphore=semaphore,
            )
        )
        for call in selected
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    persisted = 0
    skipped = 0
    failed = 0
    for entry in results:
        if isinstance(entry, BaseException):
            failed += 1
            continue
        if entry is _SectorOutcome.persisted:
            persisted += 1
        elif entry is _SectorOutcome.skipped:
            skipped += 1
        else:
            failed += 1

    return SectorFanoutOutcome(
        selected_count=len(selected),
        persisted_count=persisted,
        skipped_count=skipped,
        failed_count=failed,
    )


async def _run_one_sector(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    macro_brief: MacroBrief,
    sector_call: SectorCall,
    constituents: SectorConstituents | None,
    digest_markdown: str,
    llm_client: LlmClient,
    orchestrator: RunOrchestrator,
    http_client: httpx.AsyncClient,
    sector_fetcher: SectorSourceFetcher | None,
    semaphore: asyncio.Semaphore,
) -> _SectorOutcome:
    async with semaphore:
        sector_started = time.monotonic()
        async with session_factory() as session:
            if await _sector_brief_persisted(
                session=session,
                run_id=run_id,
                sector_entity_id=sector_call.sector_entity_id,
            ):
                _emit_resume(
                    session,
                    run_id=run_id,
                    sector=sector_call.sector_name,
                )
                await session.commit()
                return _SectorOutcome.persisted

            if constituents is None:
                _emit_skip(
                    session,
                    run_id=run_id,
                    sector=sector_call.sector_name,
                    reason="no constituents configured",
                )
                await session.commit()
                return _SectorOutcome.skipped

            # The persisted-check SELECT opens an implicit transaction; the
            # ingestion helpers reached from fetch_sector_evidence require no
            # active transaction because they each open their own.
            await session.rollback()

            evidence_result = await fetch_sector_evidence(
                session=session,
                run_id=run_id,
                sector_call=sector_call,
                constituents=constituents,
                http_client=http_client,
                fetcher=sector_fetcher,
            )
            if not evidence_result.chunks:
                _emit_skip(
                    session,
                    run_id=run_id,
                    sector=sector_call.sector_name,
                    reason="no evidence",
                )
                await session.commit()
                return _SectorOutcome.skipped

            try:
                extraction = await extract_sector_chunks(
                    session_factory=session_factory,
                    run_id=run_id,
                    chunks=evidence_result.chunks,
                    llm_complete=llm_client.complete,
                    orchestrator_pause=orchestrator.pause,
                    orchestrator_fail=orchestrator.fail,
                )
                await persist_sector_candidates(
                    session=session,
                    run_id=run_id,
                    extraction_results=extraction.results,
                )

                evidence_ids = [e.evidence_id for e in evidence_result.evidence]

                initial = await call_sector_synthesis(
                    session=session,
                    run_id=run_id,
                    macro_brief=macro_brief,
                    sector_call=sector_call,
                    digest_markdown=digest_markdown,
                    chunks=evidence_result.chunks,
                    evidence_ids=evidence_ids,
                    llm_complete=llm_client.complete,
                    orchestrator_pause=orchestrator.pause,
                    orchestrator_fail=orchestrator.fail,
                    regeneration_feedback=None,
                )

                async def regenerate(reasons: list[str]) -> SectorBrief:
                    return await call_sector_synthesis(
                        session=session,
                        run_id=run_id,
                        macro_brief=macro_brief,
                        sector_call=sector_call,
                        digest_markdown=digest_markdown,
                        chunks=evidence_result.chunks,
                        evidence_ids=evidence_ids,
                        llm_complete=llm_client.complete,
                        orchestrator_pause=orchestrator.pause,
                        orchestrator_fail=orchestrator.fail,
                        regeneration_feedback=reasons,
                    )

                regen = await run_sector_regen_loop(
                    session=session,
                    run_id=run_id,
                    initial_brief=initial,
                    chunks=evidence_result.chunks,
                    sector_call=sector_call,
                    regenerate=regenerate,
                )

                judge_public: JudgePublic
                if regen.brief.verifier_status is VerifierStatus.quote_unverified:
                    judge_public = JudgePublic(
                        status=JudgeStatus.not_run, reasons=[], call_id=None
                    )
                else:
                    judge_outcome = await run_judge(
                        session=session,
                        run_id=run_id,
                        brief=regen.brief,
                        brief_kind="sector",
                        chunks=evidence_result.chunks,
                        llm_complete=llm_client.complete,
                        orchestrator_pause=orchestrator.pause,
                        orchestrator_fail=orchestrator.fail,
                    )
                    judge_public = judge_outcome.public

                wall_clock_ms = int((time.monotonic() - sector_started) * 1000)
                resolved_brief = await resolve_sector_company_entity_ids(
                    session=session,
                    brief=regen.brief,
                )
                await persist_sector_brief(
                    session=session,
                    run_id=run_id,
                    brief=resolved_brief,
                    judge=judge_public,
                    wall_clock_ms=wall_clock_ms,
                )
                await session.commit()
                return _SectorOutcome.persisted
            except (FunnelResearchError, ExtractionBudgetHaltError) as exc:
                _emit_fail(
                    session,
                    run_id=run_id,
                    sector=sector_call.sector_name,
                    reason=str(exc),
                )
                await session.commit()
                return _SectorOutcome.failed


async def _sector_brief_persisted(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    sector_entity_id: uuid.UUID,
) -> bool:
    row_id = (
        await session.execute(
            select(SectorBriefRow.id)
            .where(SectorBriefRow.run_id == run_id)
            .where(SectorBriefRow.sector_entity_id == sector_entity_id)
        )
    ).scalar_one_or_none()
    return row_id is not None


def _emit_resume(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    sector: str,
) -> None:
    emit_run_event(
        session,
        run_id=run_id,
        level=RunEventLevel.info,
        message=f"sector {sector!r} resumed from persisted brief",
        data={"event": "sector_resumed", "sector": sector},
    )


def _emit_skip(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    sector: str,
    reason: str,
) -> None:
    emit_run_event(
        session,
        run_id=run_id,
        level=RunEventLevel.warn,
        message=f"sector {sector!r} skipped: {reason}",
        data={"event": "sector_skipped", "sector": sector, "reason": reason},
    )


def _emit_fail(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    sector: str,
    reason: str,
) -> None:
    emit_run_event(
        session,
        run_id=run_id,
        level=RunEventLevel.warn,
        message=f"sector {sector!r} failed: {reason}",
        data={"event": "sector_failed", "sector": sector, "reason": reason},
    )


__all__ = [
    "SECTOR_FANOUT_CONCURRENCY",
    "SectorFanoutOutcome",
    "run_sector_fanout",
]
