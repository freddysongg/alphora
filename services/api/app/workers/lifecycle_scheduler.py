import asyncio
import signal
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.session import session_factory as default_session_factory
from app.logging import configure_logging, get_logger
from app.services.hypothesis import run_lifecycle_sweep
from app.services.hypothesis.lifecycle import LifecycleSweepReport

_logger = get_logger(__name__)

ClockFn = Callable[[], datetime]


def _default_clock() -> datetime:
    return datetime.now(UTC)


class LifecycleScheduler:
    """Wakes periodically and runs `run_lifecycle_sweep` against open hypotheses."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        interval_seconds: float = 3600.0,
        clock: ClockFn = _default_clock,
    ) -> None:
        self._session_factory = session_factory
        self._interval_seconds = interval_seconds
        self._clock = clock

    async def run_once(self) -> LifecycleSweepReport:
        async with self._session_factory() as session:
            report = await run_lifecycle_sweep(session=session, now=self._clock())
            await session.commit()
        _logger.info(
            "lifecycle_scheduler_tick",
            expired=len(report.expired_ids),
            archived_belief_floor=len(report.archived_belief_floor_ids),
            validated=len(report.validated_ids),
            falsified=len(report.falsified_ids),
            stagnation_flagged=len(report.stagnation_flagged_ids),
        )
        return report

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        _logger.info(
            "lifecycle_scheduler_started", interval_seconds=self._interval_seconds
        )
        while not stop_event.is_set():
            try:
                await self.run_once()
            except Exception as exc:
                _logger.exception("lifecycle_scheduler_tick_failed", error=str(exc))
            await _wait_or_stop(stop_event, self._interval_seconds)
        _logger.info("lifecycle_scheduler_stopped")


async def _wait_or_stop(stop_event: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        return


def main() -> None:
    configure_logging()
    asyncio.run(_run())


async def _run() -> None:
    settings = get_settings()
    if not settings.lifecycle_sweep_enabled:
        _logger.info("lifecycle_scheduler_disabled")
        return
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())
    scheduler = LifecycleScheduler(
        session_factory=default_session_factory,
        interval_seconds=float(settings.lifecycle_sweep_interval_seconds),
    )
    await scheduler.run_forever(stop_event)


if __name__ == "__main__":
    main()


__all__ = ["LifecycleScheduler", "main"]
