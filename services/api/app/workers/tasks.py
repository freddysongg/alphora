import asyncio
from uuid import UUID

import httpx
from openai import AsyncOpenAI
from sqlalchemy import select

from app.config import get_settings
from app.db.models_runs import ResearchRun, Strategy
from app.db.session import session_factory
from app.services.hypothesis import OpenAiEmbedder
from app.services.llm.client import LlmClient
from app.services.run_orchestrator import RunOrchestrator
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
    """
    run_id = UUID(run_id_hex)
    asyncio.run(_dispatch(run_id))


def _build_openai_client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("openai_api_key is not configured")
    return AsyncOpenAI(api_key=settings.openai_api_key)


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
