import asyncio
from collections.abc import AsyncIterator
from datetime import date
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from sqlalchemy import select

from app.db.models_llm import LlmCallLog
from app.db.models_runs import ResearchRun, RunStatus
from app.db.session import session_factory
from app.services.llm import LlmClient, LlmMessage
from app.services.redis_lock import (
    make_redis_budget_lock_factory,
    reset_local_budget_lock_registry,
)


def _fake_response() -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            prompt_tokens_details=SimpleNamespace(cached_tokens=0),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
        ),
    )


class _FakeChatCompletions:
    async def create(self, **_: Any) -> Any:
        return _fake_response()


class _FakeOpenAi:
    chat = SimpleNamespace(completions=_FakeChatCompletions())


async def _seed_run() -> UUID:
    async with session_factory() as session:
        run = ResearchRun(
            ticker="AAPL",
            trade_date=date(2026, 5, 19),
            status=RunStatus.running,
            config={},
        )
        session.add(run)
        await session.commit()
        return run.id


@pytest.fixture(autouse=True)
def _clean_local_registry() -> None:
    reset_local_budget_lock_registry()


@pytest_asyncio.fixture
async def fake_redis() -> AsyncIterator[FakeRedis]:
    client = FakeRedis(decode_responses=False)
    try:
        yield client
    finally:
        await client.flushall()
        await client.aclose()


@pytest.mark.usefixtures("initialized_schema")
async def test_llm_client_serializes_per_run_with_redis_lock(
    fake_redis: FakeRedis,
) -> None:
    run_id = await _seed_run()
    fake_openai = _FakeOpenAi()
    client = LlmClient(
        openai_client=fake_openai,  # type: ignore[arg-type]
        budget_lock_factory=make_redis_budget_lock_factory(fake_redis),
    )

    async def call(i: int) -> None:
        async with session_factory() as session:
            await client.complete(
                session=session,
                messages=[LlmMessage(role="user", content=f"hello {i}")],
                model="gpt-4o-mini",
                run_id=run_id,
            )

    await asyncio.gather(*(call(i) for i in range(4)))

    async with session_factory() as session:
        logs = list(
            (
                await session.execute(
                    select(LlmCallLog).where(LlmCallLog.run_id == run_id)
                )
            )
            .scalars()
            .all()
        )
    assert len(logs) == 4
    assert all(log.cost_usd > 0 for log in logs)


@pytest.mark.usefixtures("initialized_schema")
async def test_llm_client_default_factory_is_local() -> None:
    run_id = await _seed_run()
    fake_openai = _FakeOpenAi()
    client = LlmClient(openai_client=fake_openai)  # type: ignore[arg-type]

    async with session_factory() as session:
        await client.complete(
            session=session,
            messages=[LlmMessage(role="user", content="hello")],
            model="gpt-4o-mini",
            run_id=run_id,
        )

    async with session_factory() as session:
        logs = list(
            (
                await session.execute(
                    select(LlmCallLog).where(LlmCallLog.run_id == run_id)
                )
            )
            .scalars()
            .all()
        )
    assert len(logs) == 1
