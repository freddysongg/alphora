import time
import uuid
from collections.abc import Awaitable, Callable, MutableMapping

import httpx
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_runs import ResearchRun, RunStatus
from app.schemas.extraction import BootstrappedEntity, EvidenceChunkRef
from app.schemas.macro_brief import MacroBrief, MacroBriefScope, VerifierStatus
from app.schemas.sector_brief import JudgePublic, JudgeStatus
from app.services.entity_bootstrap.gics_sectors import load_top_level_sector_names
from app.services.llm.client import LlmClient, LlmCompletionResult
from app.services.run_events import emit_stage_event
from app.services.run_orchestrator import RunOrchestrator, resolve_stage_position
from app.services.strategies.funnel_research._bootstrap import run as bootstrap_run
from app.services.strategies.funnel_research._digest import build_digest, render_markdown
from app.services.strategies.funnel_research._errors import FunnelResearchError
from app.services.strategies.funnel_research._hypotheses import persist_hypotheses
from app.services.strategies.funnel_research._ingest import (
    SourceFetcher,
    default_fetcher,
    run_ingest,
)
from app.services.strategies.funnel_research._judge import run_judge
from app.services.strategies.funnel_research._llm_call import call_synthesis
from app.services.strategies.funnel_research._persist import (
    mark_run_succeeded,
    persist_macro_brief,
)
from app.services.strategies.funnel_research._themes import promote_themes
from app.services.strategies.funnel_research._verifier import (
    RegenLoopResult,
    run_regen_loop,
    verify_once,
)
from app.services.strategies.funnel_research.config import MAX_REGENERATIONS
from app.services.strategies.funnel_research.sector import (
    SectorFanoutOutcome,
    run_sector_fanout,
)
from app.services.strategies.funnel_research.sector.evidence import (
    SectorSourceFetcher,
)
from app.services.strategies.funnel_research.sector_constituents import (
    SectorConstituents,
    load_sector_constituents,
)

_LlmCompleteCallable = Callable[..., Awaitable[LlmCompletionResult]]
_MacroRegenerateCallable = Callable[[list[str]], Awaitable[MacroBrief]]


def _emit_funnel_stage(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    stage_name: str,
    message: str,
) -> None:
    index, total = resolve_stage_position(
        strategy="funnel_research", stage_name=stage_name
    )
    emit_stage_event(
        session,
        run_id=run_id,
        stage_name=stage_name,
        stage_index=index,
        total_stages=total,
        message=message,
    )


def _index_sectors(entities: list[BootstrappedEntity]) -> dict[str, uuid.UUID]:
    return {entity.canonical_name: entity.entity_id for entity in entities}


async def _judge_macro_with_optional_regen(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    regen_result: RegenLoopResult,
    chunks: list[EvidenceChunkRef],
    sector_entity_ids: dict[str, uuid.UUID],
    allowed_sector_names: list[str],
    llm_complete: _LlmCompleteCallable,
    regenerate: _MacroRegenerateCallable,
) -> tuple[MacroBrief, JudgePublic]:
    """Run the LLM judge over the deterministically verified brief.

    On `quote_unverified`, skips the judge and returns `not_run`. On `flagged`
    with remaining regen budget, attempts one more synthesis with judge
    reasons, re-runs the deterministic verifier, and re-runs the judge if the
    new brief still verifies; otherwise keeps the original verified brief and
    the flagged judge verdict.
    """
    brief = regen_result.brief
    if brief.verifier_status is VerifierStatus.quote_unverified:
        return brief, JudgePublic(
            status=JudgeStatus.not_run, reasons=[], call_id=None
        )

    judge_outcome = await run_judge(
        session=session,
        run_id=run_id,
        brief=brief,
        brief_kind="macro",
        chunks=chunks,
        llm_complete=llm_complete,
    )
    if (
        judge_outcome.public.status is not JudgeStatus.flagged
        or not judge_outcome.regenerate_reasons
        or regen_result.regeneration_count >= MAX_REGENERATIONS
    ):
        return brief, judge_outcome.public

    new_brief_raw = await regenerate(judge_outcome.regenerate_reasons)
    verify_result = verify_once(
        brief=new_brief_raw,
        chunks=chunks,
        sector_entity_ids=sector_entity_ids,
        allowed_sector_names=allowed_sector_names,
    )
    if not verify_result.is_valid:
        return brief, judge_outcome.public

    refreshed = new_brief_raw.model_copy(
        update={
            "verifier_status": VerifierStatus.verified,
            "regeneration_count": regen_result.regeneration_count + 1,
        }
    )
    second_outcome = await run_judge(
        session=session,
        run_id=run_id,
        brief=refreshed,
        brief_kind="macro",
        chunks=chunks,
        llm_complete=llm_complete,
    )
    return refreshed, second_outcome.public


async def run_macro_brief(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    llm_client: LlmClient,
    orchestrator: RunOrchestrator,
    http_client: httpx.AsyncClient,
    fetcher: SourceFetcher | None = None,
    sector_fetcher: SectorSourceFetcher | None = None,
    sector_constituents: dict[str, SectorConstituents] | None = None,
    chunk_id_capture: MutableMapping[str, uuid.UUID] | None = None,
) -> None:
    """Execute the funnel_research strategy for one run.

    Stages ingest -> digest -> synthesize -> verify -> sector_fanout ->
    consolidate -> succeeded. Budget pause/kill is routed through the
    injected orchestrator. Failures in source clients are isolated to
    warn-level events; total source failure, invalid scope, or all sector
    fan-outs failing marks the run as failed via orchestrator.fail.
    """
    active_fetcher = fetcher or default_fetcher()
    constituents = (
        sector_constituents
        if sector_constituents is not None
        else load_sector_constituents()
    )
    started = time.monotonic()
    try:
        await _run_funnel(
            session_factory=session_factory,
            run_id=run_id,
            llm_client=llm_client,
            orchestrator=orchestrator,
            http_client=http_client,
            fetcher=active_fetcher,
            sector_fetcher=sector_fetcher,
            sector_constituents=constituents,
            chunk_id_capture=chunk_id_capture,
            started=started,
        )
    except FunnelResearchError as exc:
        await orchestrator.fail(run_id=run_id, reason=str(exc))
        raise
    except Exception as exc:
        await orchestrator.fail(run_id=run_id, reason=f"unexpected failure: {exc}")
        raise


async def _run_funnel(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    llm_client: LlmClient,
    orchestrator: RunOrchestrator,
    http_client: httpx.AsyncClient,
    fetcher: SourceFetcher,
    sector_fetcher: SectorSourceFetcher | None,
    sector_constituents: dict[str, SectorConstituents],
    chunk_id_capture: MutableMapping[str, uuid.UUID] | None,
    started: float,
) -> None:
    active_fetcher = fetcher

    async with session_factory() as session:
        run = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run_id))
        ).scalar_one()
        try:
            scope = MacroBriefScope.model_validate(run.scope_payload or {})
        except ValidationError as exc:
            await orchestrator.fail(run_id=run_id, reason=f"invalid scope: {exc}")
            return

        if run.status not in {RunStatus.queued, RunStatus.running}:
            return
        run.status = RunStatus.running
        _emit_funnel_stage(
            session,
            run_id=run_id,
            stage_name="ingest",
            message="stage 1/7: ingest",
        )
        await session.commit()

    async with session_factory() as session:
        try:
            entities = await bootstrap_run(session=session)
        except Exception as exc:
            await orchestrator.fail(
                run_id=run_id, reason=f"sector bootstrap failed: {exc}"
            )
            return
        sector_entity_ids = _index_sectors(entities)

        try:
            ingest_result = await run_ingest(
                session=session,
                run_id=run_id,
                http_client=http_client,
                fetcher=active_fetcher,
            )
        except FunnelResearchError as exc:
            await session.commit()
            await orchestrator.fail(run_id=run_id, reason=str(exc))
            return
        await session.commit()

    async with session_factory() as session:
        allowed_sector_names = await load_top_level_sector_names(session=session)

    if chunk_id_capture is not None and ingest_result.chunks:
        chunk_id_capture["__chunk_id__"] = ingest_result.chunks[0].chunk_id
        for name, entity_id in sector_entity_ids.items():
            chunk_id_capture[name] = entity_id

    async with session_factory() as session:
        _emit_funnel_stage(
            session,
            run_id=run_id,
            stage_name="digest",
            message="stage 2/7: digest",
        )
        await session.commit()

    digest_markdown = render_markdown(build_digest(ingest_result.payloads))
    evidence_ids = [evidence.evidence_id for evidence in ingest_result.evidence]

    async with session_factory() as session:
        _emit_funnel_stage(
            session,
            run_id=run_id,
            stage_name="synthesize",
            message="stage 3/7: synthesize",
        )
        await session.commit()

    async with session_factory() as session:
        try:
            initial_brief = await call_synthesis(
                session=session,
                run_id=run_id,
                scope=scope,
                digest_markdown=digest_markdown,
                chunks=ingest_result.chunks,
                sector_entity_ids=sector_entity_ids,
                llm_complete=llm_client.complete,
                orchestrator_pause=orchestrator.pause,
                orchestrator_fail=orchestrator.fail,
                evidence_ids=evidence_ids,
                regeneration_feedback=None,
            )
        except FunnelResearchError:
            await session.commit()
            raise

        _emit_funnel_stage(
            session,
            run_id=run_id,
            stage_name="verify",
            message="stage 4/7: verify",
        )

        async def regenerate(reasons: list[str]) -> MacroBrief:
            return await call_synthesis(
                session=session,
                run_id=run_id,
                scope=scope,
                digest_markdown=digest_markdown,
                chunks=ingest_result.chunks,
                sector_entity_ids=sector_entity_ids,
                llm_complete=llm_client.complete,
                orchestrator_pause=orchestrator.pause,
                orchestrator_fail=orchestrator.fail,
                evidence_ids=evidence_ids,
                regeneration_feedback=reasons,
            )

        regen_result = await run_regen_loop(
            session=session,
            run_id=run_id,
            initial_brief=initial_brief,
            chunks=ingest_result.chunks,
            sector_entity_ids=sector_entity_ids,
            regenerate=regenerate,
            allowed_sector_names=allowed_sector_names,
        )

        macro_brief, macro_judge = await _judge_macro_with_optional_regen(
            session=session,
            run_id=run_id,
            regen_result=regen_result,
            chunks=ingest_result.chunks,
            sector_entity_ids=sector_entity_ids,
            allowed_sector_names=allowed_sector_names,
            llm_complete=llm_client.complete,
            regenerate=regenerate,
        )
        await session.commit()

    async with session_factory() as session:
        await persist_hypotheses(
            session=session,
            run_id=run_id,
            proposed=list(macro_brief.proposed_hypotheses),
        )
        wall_clock_ms = int((time.monotonic() - started) * 1000)
        await persist_macro_brief(
            session=session,
            run_id=run_id,
            brief=macro_brief,
            wall_clock_ms=wall_clock_ms,
            mark_succeeded=False,
            judge=macro_judge,
        )
        await session.commit()

    async with session_factory() as session:
        _emit_funnel_stage(
            session,
            run_id=run_id,
            stage_name="sector_fanout",
            message="stage 5/7: sector_fanout",
        )
        await session.commit()

    fanout_outcome = await run_sector_fanout(
        session_factory=session_factory,
        run_id=run_id,
        macro_brief=macro_brief,
        digest_markdown=digest_markdown,
        sector_constituents=sector_constituents,
        llm_client=llm_client,
        orchestrator=orchestrator,
        http_client=http_client,
        sector_fetcher=sector_fetcher,
    )

    if _all_sectors_failed(fanout_outcome):
        await orchestrator.fail(
            run_id=run_id, reason="all sector fan-outs failed"
        )
        return

    async with session_factory() as session:
        _emit_funnel_stage(
            session,
            run_id=run_id,
            stage_name="consolidate",
            message="stage 6/7: consolidate",
        )
        await promote_themes(session=session, run_id=run_id)
        await session.commit()

    async with session_factory() as session:
        wall_clock_ms = int((time.monotonic() - started) * 1000)
        await mark_run_succeeded(
            session=session,
            run_id=run_id,
            wall_clock_ms=wall_clock_ms,
        )
        await session.commit()


def _all_sectors_failed(outcome: SectorFanoutOutcome) -> bool:
    return (
        outcome.selected_count > 0
        and outcome.failed_count == outcome.selected_count
    )


__all__ = ["run_macro_brief"]
