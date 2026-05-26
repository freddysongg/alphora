"""Long-lived worker that runs the ApprovalExpirySweeper.

Pattern mirrors `lifecycle_scheduler.py`. Config-gated via
`Settings.approval_expiry_sweeper_enabled`; interval via
`Settings.approval_expiry_sweeper_interval_seconds`.

Entry point:
    services/api/.venv/bin/python -m app.workers.approval_expiry_scheduler
"""
from __future__ import annotations

import asyncio
import signal

from app.config import get_settings
from app.db.session import session_factory as default_session_factory
from app.logging import configure_logging, get_logger
from app.services.approval_expiry_sweeper import ApprovalExpirySweeper

_logger = get_logger(__name__)


def main() -> None:
    configure_logging()
    asyncio.run(_run())


async def _run() -> None:
    settings = get_settings()
    if not settings.approval_expiry_sweeper_enabled:
        _logger.info("approval_expiry_sweeper_disabled")
        return
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())
    sweeper = ApprovalExpirySweeper(
        session_factory=default_session_factory,
        interval_seconds=float(settings.approval_expiry_sweeper_interval_seconds),
    )
    await sweeper.run_forever(stop_event)


if __name__ == "__main__":
    main()


__all__ = ["main"]
