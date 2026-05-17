import asyncio
import signal
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import session_factory as default_session_factory
from app.logging import configure_logging, get_logger
from app.services.market_clock import is_us_market_open
from app.services.paper_filler import FillResult, PaperFiller
from app.services.quote_service import QuoteService, StubQuoteService

_logger = get_logger(__name__)

ClockFn = Callable[[], datetime]


def _default_clock() -> datetime:
    return datetime.now(UTC)


class PaperScheduler:
    """Wakes periodically and fills any pending market orders when US equities are open."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        quote_service: QuoteService,
        interval_seconds: float = 60.0,
        clock: ClockFn = _default_clock,
    ) -> None:
        self._interval_seconds = interval_seconds
        self._filler = PaperFiller(
            session_factory=session_factory, quote_service=quote_service
        )
        self._clock = clock

    async def run_once(self) -> FillResult:
        now = self._clock()
        if not is_us_market_open(now):
            _logger.debug("paper_scheduler_market_closed", now=now.isoformat())
            return FillResult()
        result = await self._filler.fill_open_orders()
        _logger.info(
            "paper_scheduler_tick",
            filled=result.filled,
            rejected=result.rejected,
            skipped=result.skipped,
            error_count=len(result.errors),
        )
        return result

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        _logger.info(
            "paper_scheduler_started", interval_seconds=self._interval_seconds
        )
        while not stop_event.is_set():
            try:
                await self.run_once()
            except Exception as exc:
                _logger.exception("paper_scheduler_tick_failed", error=str(exc))
            await _wait_or_stop(stop_event, self._interval_seconds)
        _logger.info("paper_scheduler_stopped")


async def _wait_or_stop(stop_event: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        return


def main() -> None:
    configure_logging()
    asyncio.run(_run())


async def _run() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())
    scheduler = PaperScheduler(
        session_factory=default_session_factory,
        quote_service=StubQuoteService(),
    )
    await scheduler.run_forever(stop_event)


if __name__ == "__main__":
    main()


__all__ = ["PaperScheduler", "main"]
