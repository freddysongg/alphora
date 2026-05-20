"""Stage 3 company fan-out orchestrator.

Selects the top non-neutral company ideas from verified sector briefs, runs
the per-company pipeline (evidence fetch → extraction → graph persist →
synthesis → regen → judge → persist) under bounded concurrency, and reports
aggregate counts back to the parent run. The parent orchestrator decides
whether to fail the run based on the outcome (`failed_count == selected_count`).

Per-company progress is emitted as `info`-level run events on the parent run.
Stage events are not emitted per company — the UI consumes a single timeline.
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

from app.db.models_company import CompanyThesis as CompanyThesisRow
from app.db.models_runs import RunEventLevel
from app.schemas.company_thesis import CompanyThesis
from app.schemas.macro_brief import VerifierStatus
from app.schemas.sector_brief import (
    JudgePublic,
    JudgeStatus,
    SectorBrief,
    SectorBriefPublic,
)
from app.services.extraction import ExtractionBudgetHaltError
from app.services.llm.client import LlmClient
from app.services.run_events import emit_run_event
from app.services.run_orchestrator import RunOrchestrator
from app.services.strategies.funnel_research._errors import FunnelResearchError
from app.services.strategies.funnel_research._judge import run_judge
from app.services.strategies.funnel_research.company.evidence import (
    CompanySourceFetcher,
    fetch_company_evidence,
)
from app.services.strategies.funnel_research.company.extraction import (
    extract_company_chunks,
)
from app.services.strategies.funnel_research.company.graph import (
    persist_company_candidates,
)
from app.services.strategies.funnel_research.company.llm_call import (
    call_company_synthesis,
)
from app.services.strategies.funnel_research.company.persist import (
    persist_company_thesis,
)
from app.services.strategies.funnel_research.company.selector import (
    MAX_COMPANY_DEEP_DIVES,
    CompanyIdea,
    select_companies,
)
from app.services.strategies.funnel_research.company.verifier import (
    run_company_regen_loop,
)

COMPANY_FANOUT_CONCURRENCY = 2


class _CompanyOutcome(StrEnum):
    persisted = "persisted"
    skipped = "skipped"
    failed = "failed"


@dataclass(frozen=True)
class CompanyResolution:
    company_entity_id: uuid.UUID
    cik: str | None


@dataclass(frozen=True)
class CompanyFanoutOutcome:
    selected_count: int
    persisted_count: int
    skipped_count: int
    failed_count: int


def company_resolution_key(idea: CompanyIdea) -> str:
    """Return the dedupe/lookup key matching `select_companies` behavior."""
    if idea.ticker:
        return f"ticker:{idea.ticker}"
    import re
    import unicodedata

    name = (
        unicodedata.normalize("NFKD", idea.company_name)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    normalized = re.sub(r"\s+", " ", name.lower()).strip()
    return f"name:{normalized}"


async def run_company_fanout(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    sector_briefs: list[SectorBriefPublic],
    digest_markdown: str,
    company_resolutions: dict[str, CompanyResolution],
    llm_client: LlmClient,
    orchestrator: RunOrchestrator,
    http_client: httpx.AsyncClient,
    company_fetcher: CompanySourceFetcher | None = None,
    max_companies: int = MAX_COMPANY_DEEP_DIVES,
    concurrency: int = COMPANY_FANOUT_CONCURRENCY,
) -> CompanyFanoutOutcome:
    """Run company fan-out for a set of verified sector briefs.

    Returns aggregate counts: selected (≤ max), persisted, skipped (no
    resolution / no evidence), failed (synthesis/extraction error). Parent
    decides whether to fail the run based on the counts.
    """
    selected = select_companies(sector_briefs, max_count=max_companies)
    if not selected:
        return CompanyFanoutOutcome(
            selected_count=0, persisted_count=0, skipped_count=0, failed_count=0
        )

    sector_brief_by_id: dict[uuid.UUID, SectorBrief] = {
        public.brief.sector_entity_id: public.brief for public in sector_briefs
    }

    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        asyncio.create_task(
            _run_one_company(
                session_factory=session_factory,
                run_id=run_id,
                company_idea=idea,
                resolution=company_resolutions.get(company_resolution_key(idea)),
                sector_brief=sector_brief_by_id.get(idea.sector_entity_id),
                digest_markdown=digest_markdown,
                llm_client=llm_client,
                orchestrator=orchestrator,
                http_client=http_client,
                company_fetcher=company_fetcher,
                semaphore=semaphore,
            )
        )
        for idea in selected
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    persisted = 0
    skipped = 0
    failed = 0
    for entry in results:
        if isinstance(entry, BaseException):
            failed += 1
            continue
        if entry is _CompanyOutcome.persisted:
            persisted += 1
        elif entry is _CompanyOutcome.skipped:
            skipped += 1
        else:
            failed += 1

    return CompanyFanoutOutcome(
        selected_count=len(selected),
        persisted_count=persisted,
        skipped_count=skipped,
        failed_count=failed,
    )


async def _run_one_company(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    company_idea: CompanyIdea,
    resolution: CompanyResolution | None,
    sector_brief: SectorBrief | None,
    digest_markdown: str,
    llm_client: LlmClient,
    orchestrator: RunOrchestrator,
    http_client: httpx.AsyncClient,
    company_fetcher: CompanySourceFetcher | None,
    semaphore: asyncio.Semaphore,
) -> _CompanyOutcome:
    async with semaphore:
        company_started = time.monotonic()
        async with session_factory() as session:
            if resolution is not None and await _company_thesis_persisted(
                session=session,
                run_id=run_id,
                company_entity_id=resolution.company_entity_id,
            ):
                _emit_resume(
                    session,
                    run_id=run_id,
                    company=company_idea.company_name,
                )
                await session.commit()
                return _CompanyOutcome.persisted

            if resolution is None:
                _emit_skip(
                    session,
                    run_id=run_id,
                    company=company_idea.company_name,
                    reason="no resolution available",
                )
                await session.commit()
                return _CompanyOutcome.skipped

            if sector_brief is None:
                _emit_skip(
                    session,
                    run_id=run_id,
                    company=company_idea.company_name,
                    reason="parent sector brief missing",
                )
                await session.commit()
                return _CompanyOutcome.skipped

            # The persisted-check SELECT opens an implicit transaction; the
            # ingestion helpers reached from fetch_company_evidence require no
            # active transaction because they each open their own.
            await session.rollback()

            evidence_result = await fetch_company_evidence(
                session=session,
                run_id=run_id,
                company_idea=company_idea,
                cik=resolution.cik,
                http_client=http_client,
                fetcher=company_fetcher,
            )
            if not evidence_result.chunks:
                _emit_skip(
                    session,
                    run_id=run_id,
                    company=company_idea.company_name,
                    reason="no evidence",
                )
                await session.commit()
                return _CompanyOutcome.skipped

            try:
                extraction = await extract_company_chunks(
                    session_factory=session_factory,
                    run_id=run_id,
                    chunks=evidence_result.chunks,
                    llm_complete=llm_client.complete,
                    orchestrator_pause=orchestrator.pause,
                    orchestrator_fail=orchestrator.fail,
                )
                await persist_company_candidates(
                    session=session,
                    run_id=run_id,
                    extraction_results=extraction.results,
                )

                evidence_ids = [e.evidence_id for e in evidence_result.evidence]

                initial = await call_company_synthesis(
                    session=session,
                    run_id=run_id,
                    company_idea=company_idea,
                    company_entity_id=resolution.company_entity_id,
                    sector_brief=sector_brief,
                    digest_markdown=digest_markdown,
                    chunks=evidence_result.chunks,
                    evidence_ids=evidence_ids,
                    llm_complete=llm_client.complete,
                    orchestrator_pause=orchestrator.pause,
                    orchestrator_fail=orchestrator.fail,
                    regeneration_feedback=None,
                )

                async def regenerate(reasons: list[str]) -> CompanyThesis:
                    return await call_company_synthesis(
                        session=session,
                        run_id=run_id,
                        company_idea=company_idea,
                        company_entity_id=resolution.company_entity_id,
                        sector_brief=sector_brief,
                        digest_markdown=digest_markdown,
                        chunks=evidence_result.chunks,
                        evidence_ids=evidence_ids,
                        llm_complete=llm_client.complete,
                        orchestrator_pause=orchestrator.pause,
                        orchestrator_fail=orchestrator.fail,
                        regeneration_feedback=reasons,
                    )

                regen = await run_company_regen_loop(
                    session=session,
                    run_id=run_id,
                    initial_thesis=initial,
                    chunks=evidence_result.chunks,
                    company_idea=company_idea,
                    company_entity_id=resolution.company_entity_id,
                    regenerate=regenerate,
                )

                judge_public: JudgePublic
                if regen.thesis.verifier_status is VerifierStatus.quote_unverified:
                    judge_public = JudgePublic(
                        status=JudgeStatus.not_run, reasons=[], call_id=None
                    )
                else:
                    judge_outcome = await run_judge(
                        session=session,
                        run_id=run_id,
                        brief=regen.thesis,
                        brief_kind="company",
                        chunks=evidence_result.chunks,
                        llm_complete=llm_client.complete,
                        orchestrator_pause=orchestrator.pause,
                        orchestrator_fail=orchestrator.fail,
                    )
                    judge_public = judge_outcome.public

                wall_clock_ms = int((time.monotonic() - company_started) * 1000)
                await persist_company_thesis(
                    session=session,
                    run_id=run_id,
                    thesis=regen.thesis,
                    judge=judge_public,
                    wall_clock_ms=wall_clock_ms,
                )
                await session.commit()
                return _CompanyOutcome.persisted
            except (FunnelResearchError, ExtractionBudgetHaltError) as exc:
                _emit_fail(
                    session,
                    run_id=run_id,
                    company=company_idea.company_name,
                    reason=str(exc),
                )
                await session.commit()
                return _CompanyOutcome.failed


async def _company_thesis_persisted(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    company_entity_id: uuid.UUID,
) -> bool:
    row_id = (
        await session.execute(
            select(CompanyThesisRow.id)
            .where(CompanyThesisRow.run_id == run_id)
            .where(CompanyThesisRow.company_entity_id == company_entity_id)
        )
    ).scalar_one_or_none()
    return row_id is not None


def _emit_resume(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    company: str,
) -> None:
    emit_run_event(
        session,
        run_id=run_id,
        level=RunEventLevel.info,
        message=f"company {company!r} resumed from persisted thesis",
        data={"event": "company_resumed", "company": company},
    )


def _emit_skip(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    company: str,
    reason: str,
) -> None:
    emit_run_event(
        session,
        run_id=run_id,
        level=RunEventLevel.warn,
        message=f"company {company!r} skipped: {reason}",
        data={"event": "company_skipped", "company": company, "reason": reason},
    )


def _emit_fail(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    company: str,
    reason: str,
) -> None:
    emit_run_event(
        session,
        run_id=run_id,
        level=RunEventLevel.warn,
        message=f"company {company!r} failed: {reason}",
        data={"event": "company_failed", "company": company, "reason": reason},
    )


__all__ = [
    "COMPANY_FANOUT_CONCURRENCY",
    "CompanyFanoutOutcome",
    "CompanyResolution",
    "company_resolution_key",
    "run_company_fanout",
]
