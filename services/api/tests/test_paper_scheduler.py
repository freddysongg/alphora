import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from app.services.paper_filler import FillResult
from app.workers.paper_scheduler import PaperScheduler


class _RecordingFiller:
    def __init__(self, results: list[FillResult] | None = None) -> None:
        self._results = list(results) if results is not None else [FillResult()]
        self.call_count = 0

    async def fill_open_orders(self) -> FillResult:
        self.call_count += 1
        if not self._results:
            return FillResult()
        if len(self._results) == 1:
            return self._results[0]
        return self._results.pop(0)


class _RaisingThenEmptyFiller:
    def __init__(self) -> None:
        self.call_count = 0

    async def fill_open_orders(self) -> FillResult:
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("transient downstream failure")
        return FillResult()


def _fixed_clock(moment: datetime) -> Callable[[], datetime]:
    def _clock() -> datetime:
        return moment

    return _clock


async def test_run_once_skips_when_market_closed() -> None:
    saturday_noon_utc = datetime(2026, 5, 16, 12, 0, tzinfo=UTC)
    filler = _RecordingFiller()
    scheduler = PaperScheduler(filler=filler, clock=_fixed_clock(saturday_noon_utc))

    result = await scheduler.run_once()

    assert filler.call_count == 0
    assert result.filled == 0
    assert result.rejected == 0
    assert result.skipped == 0
    assert result.errors == []
    assert result.outcomes == []


async def test_run_once_calls_filler_when_market_open() -> None:
    weekday_open_utc = datetime(2026, 5, 13, 14, 0, tzinfo=UTC)
    expected = FillResult(filled=2)
    filler = _RecordingFiller(results=[expected])
    scheduler = PaperScheduler(filler=filler, clock=_fixed_clock(weekday_open_utc))

    result = await scheduler.run_once()

    assert filler.call_count == 1
    assert result is expected


async def test_run_forever_swallows_filler_exceptions_and_continues() -> None:
    weekday_open_utc = datetime(2026, 5, 13, 14, 0, tzinfo=UTC)
    filler = _RaisingThenEmptyFiller()
    scheduler = PaperScheduler(
        filler=filler,
        interval_seconds=0.01,
        clock=_fixed_clock(weekday_open_utc),
    )
    stop_event = asyncio.Event()

    task = asyncio.create_task(scheduler.run_forever(stop_event))
    try:
        await asyncio.sleep(0.1)
    finally:
        stop_event.set()
        await asyncio.wait_for(task, timeout=1.0)

    assert filler.call_count >= 2


async def test_run_forever_stops_promptly_on_event() -> None:
    weekday_open_utc = datetime(2026, 5, 13, 14, 0, tzinfo=UTC)
    filler = _RecordingFiller()
    scheduler = PaperScheduler(
        filler=filler,
        interval_seconds=10.0,
        clock=_fixed_clock(weekday_open_utc),
    )
    stop_event = asyncio.Event()

    task = asyncio.create_task(scheduler.run_forever(stop_event))
    await asyncio.sleep(0.05)
    stop_event.set()

    await asyncio.wait_for(task, timeout=1.0)
    assert task.done()
