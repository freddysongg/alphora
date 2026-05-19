import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

from app.services.redis_lock import (
    LocalBudgetLock,
    RedisBudgetLock,
    make_local_budget_lock_factory,
    make_redis_budget_lock_factory,
    reset_local_budget_lock_registry,
)


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


async def test_local_lock_serializes_same_key() -> None:
    run_id = uuid.uuid4()
    order: list[str] = []
    factory = make_local_budget_lock_factory()

    async def acquire(label: str, hold_seconds: float) -> None:
        async with factory(run_id):
            order.append(f"{label}-enter")
            await asyncio.sleep(hold_seconds)
            order.append(f"{label}-exit")

    await asyncio.gather(
        acquire("a", 0.02),
        acquire("b", 0.0),
    )
    assert order in (
        ["a-enter", "a-exit", "b-enter", "b-exit"],
        ["b-enter", "b-exit", "a-enter", "a-exit"],
    )


async def test_local_lock_distinct_keys_run_concurrently() -> None:
    run_id_one = uuid.uuid4()
    run_id_two = uuid.uuid4()
    factory = make_local_budget_lock_factory()
    enter_one = asyncio.Event()
    can_exit_one = asyncio.Event()

    async def hold_one() -> None:
        async with factory(run_id_one):
            enter_one.set()
            await can_exit_one.wait()

    async def acquire_two_quickly() -> bool:
        await enter_one.wait()
        async with factory(run_id_two):
            return True

    hold_task = asyncio.create_task(hold_one())
    other = asyncio.create_task(acquire_two_quickly())
    second_acquired = await asyncio.wait_for(other, timeout=0.5)
    assert second_acquired is True
    can_exit_one.set()
    await hold_task


async def test_local_lock_supports_none_run_id() -> None:
    factory = make_local_budget_lock_factory()
    async with factory(None):
        pass
    async with factory(None):
        pass


async def test_redis_lock_serializes_same_run(fake_redis: FakeRedis) -> None:
    run_id = uuid.uuid4()
    order: list[str] = []
    factory = make_redis_budget_lock_factory(fake_redis)

    async def acquire(label: str, hold_seconds: float) -> None:
        async with factory(run_id):
            order.append(f"{label}-enter")
            await asyncio.sleep(hold_seconds)
            order.append(f"{label}-exit")

    await asyncio.gather(
        acquire("a", 0.05),
        acquire("b", 0.0),
    )
    assert order in (
        ["a-enter", "a-exit", "b-enter", "b-exit"],
        ["b-enter", "b-exit", "a-enter", "a-exit"],
    )


async def test_redis_lock_does_not_leak_key_after_release(
    fake_redis: FakeRedis,
) -> None:
    run_id = uuid.uuid4()
    lock = RedisBudgetLock(fake_redis, run_id)
    async with lock:
        assert await fake_redis.exists(lock._key) == 1
    assert await fake_redis.exists(lock._key) == 0


async def test_redis_lock_distinct_keys_run_concurrently(
    fake_redis: FakeRedis,
) -> None:
    run_id_one = uuid.uuid4()
    run_id_two = uuid.uuid4()
    factory = make_redis_budget_lock_factory(fake_redis)
    enter_one = asyncio.Event()
    can_exit_one = asyncio.Event()

    async def hold_one() -> None:
        async with factory(run_id_one):
            enter_one.set()
            await can_exit_one.wait()

    async def acquire_two_quickly() -> bool:
        await enter_one.wait()
        async with factory(run_id_two):
            return True

    hold_task = asyncio.create_task(hold_one())
    other = asyncio.create_task(acquire_two_quickly())
    second_acquired = await asyncio.wait_for(other, timeout=0.5)
    assert second_acquired is True
    can_exit_one.set()
    await hold_task


def test_local_budget_lock_class_construction_no_run_id() -> None:
    lock = LocalBudgetLock(None)
    assert lock._key == "__global__"


def test_local_budget_lock_class_construction_with_run_id() -> None:
    run_id = uuid.UUID(int=42)
    lock = LocalBudgetLock(run_id)
    assert lock._key == str(run_id)
