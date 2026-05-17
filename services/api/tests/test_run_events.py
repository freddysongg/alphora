from collections.abc import AsyncIterator
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import models as _models  # noqa: F401
from app.db.base import Base
from app.db.models_runs import ResearchRun, RunEvent, RunEventLevel, RunStatus
from app.services.run_events import (
    COST_EVENT,
    PAUSE_EVENT,
    RESUME_EVENT,
    STAGE_EVENT,
    emit_run_event,
    emit_stage_event,
)


@pytest.fixture()
async def isolated_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield factory
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def _insert_run(factory: async_sessionmaker[AsyncSession]) -> ResearchRun:
    run = ResearchRun(
        id=uuid4(),
        ticker="AAPL",
        trade_date=date(2026, 5, 17),
        status=RunStatus.running,
        config={},
    )
    async with factory() as session:
        session.add(run)
        await session.commit()
    return run


async def test_event_constants_have_expected_values() -> None:
    assert COST_EVENT == "cost"
    assert STAGE_EVENT == "stage"
    assert PAUSE_EVENT == "pause"
    assert RESUME_EVENT == "resume"


async def test_emit_run_event_inserts_row_with_data(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run = await _insert_run(isolated_session_factory)
    payload: dict[str, object] = {"event": COST_EVENT, "model": "gpt-5", "cost_usd": "0.05"}

    async with isolated_session_factory() as session:
        emit_run_event(
            session,
            run_id=run.id,
            level=RunEventLevel.info,
            message="llm call cost $0.05",
            data=payload,
        )
        await session.commit()

    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(RunEvent).where(RunEvent.run_id == run.id))
        ).scalars().all()
        assert len(stored) == 1
        event = stored[0]
        assert event.run_id == run.id
        assert event.level == RunEventLevel.info
        assert event.message == "llm call cost $0.05"
        assert event.data == payload


async def test_emit_stage_event_uses_canonical_payload_shape(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run = await _insert_run(isolated_session_factory)

    async with isolated_session_factory() as session:
        emit_stage_event(
            session,
            run_id=run.id,
            stage_name="running",
            stage_index=1,
            total_stages=2,
        )
        await session.commit()

    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(RunEvent).where(RunEvent.run_id == run.id))
        ).scalars().one()
        assert stored.level == RunEventLevel.info
        assert "1/2" in stored.message
        assert stored.data == {
            "event": STAGE_EVENT,
            "stage_name": "running",
            "stage_index": 1,
            "total_stages": 2,
        }


async def test_emit_stage_event_accepts_custom_message(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run = await _insert_run(isolated_session_factory)

    async with isolated_session_factory() as session:
        emit_stage_event(
            session,
            run_id=run.id,
            stage_name="running",
            stage_index=1,
            total_stages=2,
            message="execution started",
        )
        await session.commit()

    async with isolated_session_factory() as session:
        stored = (
            await session.execute(select(RunEvent).where(RunEvent.run_id == run.id))
        ).scalars().one()
        assert stored.message == "execution started"
