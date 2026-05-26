"""Long-lived worker that runs the DataHealthPinger.

Pattern mirrors `approval_expiry_scheduler.py`. Config-gated via
`Settings.data_health_pinger_enabled`; interval via
`Settings.data_health_pinger_interval_seconds`.

Entry point:
    services/api/.venv/bin/python -m app.workers.data_health_scheduler
"""
from __future__ import annotations

import asyncio
import signal

from app.config import get_settings
from app.db.session import session_factory as default_session_factory
from app.logging import configure_logging, get_logger
from app.services.data_health_pinger import DataHealthPinger

_logger = get_logger(__name__)


def main() -> None:
    configure_logging()
    asyncio.run(_run())


async def _run() -> None:
    settings = get_settings()
    if not settings.data_health_pinger_enabled:
        _logger.info("data_health_pinger_disabled")
        return
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())
    pinger = DataHealthPinger(
        session_factory=default_session_factory,
        interval_seconds=float(settings.data_health_pinger_interval_seconds),
    )
    await pinger.run_forever(stop_event)


if __name__ == "__main__":
    main()


__all__ = ["main"]
