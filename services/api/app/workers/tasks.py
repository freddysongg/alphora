import asyncio
from types import TracebackType
from typing import Any
from uuid import UUID

import httpx
from openai import AsyncOpenAI
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import select

from app.config import get_settings
from app.db.models_runs import ResearchRun, Strategy
from app.db.session import session_factory
from app.logging import get_logger
from app.schemas.budget import BudgetThresholds
from app.services.budget import BudgetGuard
from app.services.data_sources_bootstrap import bootstrap_data_sources
from app.services.hypothesis import OpenAiEmbedder
from app.services.llm.client import LlmClient
from app.services.run_orchestrator import RunOrchestrator
from app.services.source_clients._registry import (
    configure_redis,
    install_request_cache,
)
from app.services.source_clients._request_cache import RequestCache
from app.services.strategies.funnel_research import (
    FunnelResearchError,
    run_macro_brief,
)

_logger = get_logger(__name__)


def execute_research_run(run_id_hex: str) -> None:
    """RQ task entrypoint for executing a single research run.

    Bridges sync RQ to the async orchestrator via asyncio.run. RQ pickles tasks
    by their fully-qualified import path so this function must remain importable
    as `app.workers.tasks.execute_research_run`.

    Dispatches on the run's strategy. Any dispatch-time failure (missing
    API key, unknown strategy) is routed through `orchestrator.fail` so the
    run row reaches `failed` instead of stranding at `queued`.

    `_run_with_source_client_runtime` constructs a fresh `AsyncRedis` client
    and `RequestCache` inside the per-job `asyncio.run` so the Redis
    connection pool is bound to the live event loop. The previous design
    cached one Redis client for the worker process lifetime, which broke
    on the second job because the first job's `asyncio.run` had already
    closed the loop the pool was bound to.
    """
    run_id = UUID(run_id_hex)
    asyncio.run(_run_with_source_client_runtime(run_id))


async def _run_with_source_client_runtime(run_id: UUID) -> None:
    redis_client = _build_async_redis_client()
    request_cache = RequestCache(ttl_seconds=300.0)
    configure_redis(redis_client)
    install_request_cache(request_cache)
    try:
        await _bootstrap_data_sources_for_run()
        await _dispatch(run_id)
    finally:
        await _persist_cache_stats(run_id=run_id, request_cache=request_cache)
        configure_redis(None)
        install_request_cache(None)
        await _close_async_redis_client(redis_client)


async def _persist_cache_stats(
    *, run_id: UUID, request_cache: RequestCache
) -> None:
    stats = request_cache.stats()
    payload: dict[str, object] = {
        "hits": stats.hits,
        "misses": stats.misses,
        "evictions": stats.evictions,
        "hit_rate": stats.hit_rate,
    }
    try:
        async with session_factory() as session:
            run = (
                await session.execute(
                    select(ResearchRun).where(ResearchRun.id == run_id)
                )
            ).scalar_one_or_none()
            if run is None:
                return
            run.source_client_cache_stats = payload
            await session.commit()
    except Exception as exc:
        _logger.warning(
            "source_client_cache_stats_persist_failed",
            run_id=str(run_id),
            error=str(exc),
        )




async def _bootstrap_data_sources_for_run() -> None:
    """Seed the canonical `data_sources` rows before dispatch.

    The bootstrap is idempotent — second and later invocations return
    `unchanged == len(KNOWN_DATA_SOURCES)` after one SELECT. Running on a
    dedicated session keeps the commit boundary isolated from the dispatch
    session so per-source-client `_resolve_source_id` lookups see the rows.
    """
    async with session_factory() as session:
        await bootstrap_data_sources(session=session)
        await session.commit()


def _build_openai_client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("openai_api_key is not configured")
    return AsyncOpenAI(api_key=settings.openai_api_key)


def _build_async_redis_client() -> AsyncRedis:
    return AsyncRedis.from_url(
        get_settings().redis_url, decode_responses=False
    )


async def _close_async_redis_client(client: AsyncRedis) -> None:
    """Release the Redis pool inside the same event loop that allocated it.

    `redis.asyncio.Redis.aclose()` is preferred when available; we fall back
    to `close()` so the worker still cleans up under older redis-py builds.
    """
    aclose = getattr(client, "aclose", None)
    if callable(aclose):
        await aclose()
        return
    await client.close()


async def _dispatch(run_id: UUID) -> None:
    strategy = await _load_strategy(run_id)
    orchestrator = RunOrchestrator(session_factory=session_factory)
    if strategy == Strategy.funnel_research.value:
        await _dispatch_funnel_research(run_id=run_id, orchestrator=orchestrator)
        return
    await orchestrator.fail(
        run_id,
        f"strategy {strategy!r} is not implemented yet",
    )


async def _dispatch_funnel_research(
    *, run_id: UUID, orchestrator: RunOrchestrator
) -> None:
    try:
        openai_client = _build_openai_client()
    except Exception as exc:
        await orchestrator.fail(
            run_id, f"failed to construct openai client: {exc}"
        )
        return
    settings = get_settings()
    thresholds = BudgetThresholds(per_stage_usd=settings.per_stage_budget_caps_usd)
    budget_guard = BudgetGuard(thresholds=thresholds)
    try:
        async with httpx.AsyncClient() as http_client:
            llm_client = LlmClient(
                openai_client=openai_client, budget_guard=budget_guard
            )
            hypothesis_embedder = OpenAiEmbedder(client=openai_client)
            await run_macro_brief(
                session_factory=session_factory,
                run_id=run_id,
                llm_client=llm_client,
                orchestrator=orchestrator,
                http_client=http_client,
                hypothesis_embedder=hypothesis_embedder,
            )
    except FunnelResearchError:
        return


async def _load_strategy(run_id: UUID) -> str:
    async with session_factory() as session:
        result = await session.execute(
            select(ResearchRun.strategy).where(ResearchRun.id == run_id)
        )
        return result.scalar_one()


def mark_run_failed_on_job_failure(
    job: Any,
    _connection: Any,
    exc_type: type[BaseException],
    exc_value: BaseException,
    _traceback: TracebackType,
) -> None:
    """RQ on_failure callback: mark the run failed when the worker dies.

    Without this, JobTimeoutException (and other unhandled exceptions in the
    worker process) leave research_runs.status frozen at 'running' because
    the orchestrator's own try/except runs inside the dying event loop.
    """
    args = getattr(job, "args", None) or ()
    if not args:
        _logger.warning("rq_on_failure_missing_run_id_hex", job_id=getattr(job, "id", None))
        return
    try:
        run_id = UUID(args[0])
    except (ValueError, TypeError) as parse_exc:
        _logger.warning(
            "rq_on_failure_invalid_run_id_hex",
            job_id=getattr(job, "id", None),
            error=str(parse_exc),
        )
        return
    reason = f"worker job failed: {exc_type.__name__}: {exc_value}"
    try:
        asyncio.run(_mark_run_failed(run_id=run_id, reason=reason))
    except Exception as cleanup_exc:
        _logger.exception(
            "rq_on_failure_mark_failed_failed",
            run_id=str(run_id),
            error=str(cleanup_exc),
        )


async def _mark_run_failed(*, run_id: UUID, reason: str) -> None:
    orchestrator = RunOrchestrator(session_factory=session_factory)
    await orchestrator.fail(run_id, reason)
