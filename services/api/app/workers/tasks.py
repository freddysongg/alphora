import asyncio
from uuid import UUID

import httpx
from openai import AsyncOpenAI
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import select

from app.config import get_settings
from app.db.models_runs import ResearchRun, Strategy
from app.db.session import session_factory
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
from app.trading_agents.adapter import TradingAgentsAdapter


def execute_research_run(run_id_hex: str) -> None:
    """RQ task entrypoint for executing a single research run.

    Bridges sync RQ to the async orchestrator via asyncio.run. RQ pickles tasks
    by their fully-qualified import path so this function must remain importable
    as `app.workers.tasks.execute_research_run`.

    Dispatches on the run's strategy. Any dispatch-time failure (missing
    API key, unknown strategy) is routed through `orchestrator.fail` so the
    run row reaches `failed` instead of stranding at `queued`.

    Installs a worker-time async Redis client into the source-client rate
    limiter registry on first dispatch so the per-source token buckets
    coordinate across processes.
    """
    run_id = UUID(run_id_hex)
    _install_async_redis_limiter()
    asyncio.run(_dispatch(run_id))


def _build_openai_client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("openai_api_key is not configured")
    return AsyncOpenAI(api_key=settings.openai_api_key)


def _install_async_redis_limiter() -> None:
    """Install the async Redis client + request cache into the registry.

    Worker boots once per task, so this runs each dispatch; the install
    is short-circuited once configured so the limiter cache does not
    thrash between dispatches. The worker process holds a single async
    Redis client and a single shared 5-minute request cache over its
    lifetime.
    """
    global _LIMITER_CONFIGURED
    if _LIMITER_CONFIGURED:
        return
    configure_redis(_get_worker_redis())
    install_request_cache(RequestCache(ttl_seconds=300.0))
    _LIMITER_CONFIGURED = True


def _get_worker_redis() -> AsyncRedis:
    global _CACHED_WORKER_REDIS
    if _CACHED_WORKER_REDIS is None:
        _CACHED_WORKER_REDIS = AsyncRedis.from_url(
            get_settings().redis_url, decode_responses=False
        )
    return _CACHED_WORKER_REDIS


_CACHED_WORKER_REDIS: AsyncRedis | None = None
_LIMITER_CONFIGURED: bool = False


async def _dispatch(run_id: UUID) -> None:
    strategy = await _load_strategy(run_id)
    adapter = TradingAgentsAdapter()
    orchestrator = RunOrchestrator(session_factory=session_factory, adapter=adapter)
    if strategy == Strategy.tradingagents.value:
        await orchestrator.execute(run_id)
        return
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
    try:
        async with httpx.AsyncClient() as http_client:
            llm_client = LlmClient(openai_client=openai_client)
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
