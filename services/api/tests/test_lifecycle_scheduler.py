"""Tests for LifecycleScheduler: run_once, run_forever exception swallow,
stop-event responsiveness, disabled-flag exit."""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType, Hypothesis, HypothesisStatus
from app.db.session import session_factory as default_session_factory
from app.workers.lifecycle_scheduler import LifecycleScheduler, _run


def _fixed_clock(moment: datetime) -> Callable[[], datetime]:
    def _clock() -> datetime:
        return moment

    return _clock


async def _seed_expired_hypothesis(
    session: AsyncSession, *, valid_until: datetime
) -> uuid.UUID:
    mirror = Entity(
        type=EntityType.hypothesis.value,
        canonical_name="claim",
        aliases=["claim"],
        external_ids={},
        attributes={},
    )
    session.add(mirror)
    await session.flush()
    hypothesis = Hypothesis(
        claim_text="claim",
        scope_entity_ids=[],
        scope_theme_ids=[],
        status=HypothesisStatus.active.value,
        belief=0.5,
        belief_history=[],
        entity_id=mirror.id,
        valid_until=valid_until,
    )
    session.add(hypothesis)
    await session.commit()
    return hypothesis.id


@pytest.mark.asyncio
async def test_run_once_invokes_sweep_and_returns_report_with_expired_id(
    initialized_schema: None,
) -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    async with default_session_factory() as session:
        hypothesis_id = await _seed_expired_hypothesis(
            session, valid_until=now - timedelta(seconds=1)
        )

    scheduler = LifecycleScheduler(
        session_factory=default_session_factory,
        interval_seconds=60.0,
        clock=_fixed_clock(now),
    )
    report = await scheduler.run_once()

    assert hypothesis_id in report.expired_ids


@pytest.mark.asyncio
async def test_run_once_commits_so_changes_persist_to_a_new_session(
    initialized_schema: None,
) -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    async with default_session_factory() as session:
        hypothesis_id = await _seed_expired_hypothesis(
            session, valid_until=now - timedelta(seconds=1)
        )

    scheduler = LifecycleScheduler(
        session_factory=default_session_factory,
        interval_seconds=60.0,
        clock=_fixed_clock(now),
    )
    await scheduler.run_once()

    async with default_session_factory() as verify:
        row = (
            await verify.execute(
                select(Hypothesis).where(Hypothesis.id == hypothesis_id)
            )
        ).scalar_one()
    assert row.status == HypothesisStatus.expired.value
    assert row.archived_at is not None
    assert row.archived_reason == "valid_until"


class _RaisingThenEmptySweep:
    """Module-level monkeypatch target: counts calls, raises once, then returns
    an empty report. The scheduler must catch the exception and retry on the
    next tick."""

    def __init__(self) -> None:
        self.call_count = 0

    async def __call__(self, *, session: AsyncSession, **_: object) -> object:
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("transient sweep failure")
        from app.services.hypothesis.lifecycle import LifecycleSweepReport

        return LifecycleSweepReport()


@pytest.mark.asyncio
async def test_run_forever_swallows_sweep_exception_and_continues(
    initialized_schema: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sweep_stub = _RaisingThenEmptySweep()
    from app.workers import lifecycle_scheduler as module

    monkeypatch.setattr(module, "run_lifecycle_sweep", sweep_stub)

    scheduler = LifecycleScheduler(
        session_factory=default_session_factory,
        interval_seconds=0.01,
    )
    stop_event = asyncio.Event()
    task = asyncio.create_task(scheduler.run_forever(stop_event))
    try:
        await asyncio.sleep(0.1)
    finally:
        stop_event.set()
        await asyncio.wait_for(task, timeout=1.0)

    assert sweep_stub.call_count >= 2


@pytest.mark.asyncio
async def test_run_forever_stops_promptly_when_stop_event_set(
    initialized_schema: None,
) -> None:
    scheduler = LifecycleScheduler(
        session_factory=default_session_factory,
        interval_seconds=10.0,
    )
    stop_event = asyncio.Event()
    task = asyncio.create_task(scheduler.run_forever(stop_event))
    await asyncio.sleep(0.05)
    stop_event.set()

    await asyncio.wait_for(task, timeout=1.0)
    assert task.done()


@pytest.mark.asyncio
async def test_run_returns_without_loop_when_lifecycle_sweep_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import Settings
    from app.workers import lifecycle_scheduler as module

    def _fake_settings() -> Settings:
        return Settings(lifecycle_sweep_enabled=False)

    monkeypatch.setattr(module, "get_settings", _fake_settings)

    invoked: dict[str, bool] = {"run_forever": False}

    class _Sentinel:
        async def run_forever(self, _: asyncio.Event) -> None:
            invoked["run_forever"] = True

    monkeypatch.setattr(module, "LifecycleScheduler", lambda **__: _Sentinel())

    await _run()

    assert invoked["run_forever"] is False
