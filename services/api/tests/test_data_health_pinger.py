"""Unit tests for DataHealthPinger.

The per-provider check coroutines are stubbed via the `health_checks` ctor arg
so these tests do not depend on httpx or any real provider client.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_data_health import ProviderCheck, ProviderCheckStatus
from app.services.data_health_pinger import (
    DataHealthPinger,
    HealthCheckResult,
    HealthCheckSkipError,
)


def _fixed_clock(now: datetime) -> Callable[[], datetime]:
    def _clock() -> datetime:
        return now

    return _clock


@pytest.mark.asyncio
async def test_success_writes_one_row(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime(2026, 5, 25, 12, 0, 0, tzinfo=UTC)

    async def ok() -> HealthCheckResult:
        return HealthCheckResult(status=ProviderCheckStatus.success, latency_ms=42)

    pinger = DataHealthPinger(
        session_factory=session_maker,
        health_checks={"sec_edgar": ok},
        clock=_fixed_clock(now),
        timeout_seconds=5.0,
    )
    report = await pinger.run_once()
    assert report.checked_count == 1
    assert report.success_count == 1
    assert report.fail_count == 0

    async with session_maker() as session:
        rows = (await session.execute(select(ProviderCheck))).scalars().all()
    assert len(rows) == 1
    assert rows[0].provider == "sec_edgar"
    assert rows[0].tool == "health"
    assert rows[0].status == ProviderCheckStatus.success
    assert rows[0].latency_ms == 42
    stored_at_naive = rows[0].at.replace(tzinfo=None)
    expected_at_naive = now.replace(tzinfo=None)
    assert stored_at_naive == expected_at_naive


@pytest.mark.asyncio
async def test_timeout_writes_failure_row(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async def hangs() -> HealthCheckResult:
        await asyncio.sleep(10)
        return HealthCheckResult(status=ProviderCheckStatus.success, latency_ms=0)

    pinger = DataHealthPinger(
        session_factory=session_maker,
        health_checks={"polygon": hangs},
        timeout_seconds=0.05,
    )
    report = await pinger.run_once()
    assert report.fail_count == 1

    async with session_maker() as session:
        rows = (await session.execute(select(ProviderCheck))).scalars().all()
    assert len(rows) == 1
    assert rows[0].provider == "polygon"
    assert rows[0].status == ProviderCheckStatus.failure
    assert rows[0].error_message == "timeout"


@pytest.mark.asyncio
async def test_error_writes_failure_row_with_short_message(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async def raises() -> HealthCheckResult:
        raise RuntimeError("boom")

    pinger = DataHealthPinger(
        session_factory=session_maker,
        health_checks={"tiingo": raises},
        timeout_seconds=5.0,
    )
    report = await pinger.run_once()
    assert report.fail_count == 1

    async with session_maker() as session:
        rows = (await session.execute(select(ProviderCheck))).scalars().all()
    assert len(rows) == 1
    assert rows[0].provider == "tiingo"
    assert rows[0].status == ProviderCheckStatus.failure
    assert "boom" in (rows[0].error_message or "")


@pytest.mark.asyncio
async def test_skip_omits_row(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async def skip() -> HealthCheckResult:
        raise HealthCheckSkipError("FRED_API_KEY unset")

    pinger = DataHealthPinger(
        session_factory=session_maker,
        health_checks={"fred": skip},
        timeout_seconds=5.0,
    )
    report = await pinger.run_once()
    assert report.checked_count == 0
    assert report.skipped_count == 1

    async with session_maker() as session:
        rows = (await session.execute(select(ProviderCheck))).scalars().all()
    assert rows == []
