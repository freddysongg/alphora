import time
import uuid
from collections.abc import MutableMapping

import httpx
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_runs import ResearchRun, RunStatus
from app.schemas.extraction import BootstrappedEntity
from app.schemas.macro_brief import MacroBrief, MacroBriefScope
from app.services.entity_bootstrap.gics_sectors import load_top_level_sector_names
from app.services.llm.client import LlmClient
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
from app.services.strategies.funnel_research._llm_call import call_synthesis
from app.services.strategies.funnel_research._persist import (
    mark_run_succeeded,
    persist_macro_brief,
)
from app.services.strategies.funnel_research._verifier import run_regen_loop


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


async def run_macro_brief(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    llm_client: LlmClient,
    orchestrator: RunOrchestrator,
    http_client: httpx.AsyncClient,
    fetcher: SourceFetcher | None = None,
    chunk_id_capture: MutableMapping[str, uuid.UUID] | None = None,
) -> None:
    """Execute Stage 1 of the funnel_research strategy for one run.

    Stages ingest -> digest -> synthesize -> verify -> succeeded. Budget
    pause/kill is routed through the injected orchestrator. Failures in
    source clients are isolated to warn-level events; total source failure
    or invalid scope marks the run as failed via orchestrator.fail.
    """
    active_fetcher = fetcher or default_fetcher()
    started = time.monotonic()
    try:
        await _run_funnel(
            session_factory=session_factory,
            run_id=run_id,
            llm_client=llm_client,
            orchestrator=orchestrator,
            http_client=http_client,
            fetcher=active_fetcher,
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
        await session.commit()

    async with session_factory() as session:
        await persist_hypotheses(
            session=session,
            run_id=run_id,
            proposed=list(regen_result.brief.proposed_hypotheses),
        )
        wall_clock_ms = int((time.monotonic() - started) * 1000)
        await persist_macro_brief(
            session=session,
            run_id=run_id,
            brief=regen_result.brief,
            wall_clock_ms=wall_clock_ms,
            mark_succeeded=False,
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

    async with session_factory() as session:
        _emit_funnel_stage(
            session,
            run_id=run_id,
            stage_name="consolidate",
            message="stage 6/7: consolidate",
        )
        await session.commit()

    async with session_factory() as session:
        wall_clock_ms = int((time.monotonic() - started) * 1000)
        await mark_run_succeeded(
            session=session,
            run_id=run_id,
            wall_clock_ms=wall_clock_ms,
        )
        await session.commit()


__all__ = ["run_macro_brief"]
