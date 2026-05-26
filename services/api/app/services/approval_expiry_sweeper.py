"""Phase 7 expiry sweeper for `pending_approvals`.

Defense-in-depth against a crashed runner: pending live rows whose
`expires_at` is in the past get flipped to `expired` so the UI shows the
right state and the operator isn't asked to act on stale rows.

The runner's own `request_approval` poll loop ALSO self-expires; this
sweeper is the fallback for cases where the runner isn't around to
self-detect (crashed, paused, restarted between issuance and expiry).

Pattern matches `app/workers/lifecycle_scheduler.py`.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_approval import PendingApprovalRow, PendingApprovalStatus
from app.logging import get_logger

_logger = get_logger(__name__)


def _default_clock() -> datetime:
    return datetime.now(UTC)


@dataclass
class ExpirySweepReport:
    expired_ids: list[UUID] = field(default_factory=list)


class ApprovalExpirySweeper:
    """Wakes periodically and flips overdue pending+live rows to expired."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        interval_seconds: float = 10.0,
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._session_factory = session_factory
        self._interval_seconds = interval_seconds
        self._clock = clock

    async def run_once(self) -> ExpirySweepReport:
        now = self._clock()
        report = ExpirySweepReport()
        async with self._session_factory() as session:
            stmt = select(PendingApprovalRow).where(
                PendingApprovalRow.status == PendingApprovalStatus.pending.value,
                PendingApprovalRow.mode == "live",
                PendingApprovalRow.expires_at.is_not(None),
                PendingApprovalRow.expires_at <= now,
            )
            rows = (await session.execute(stmt)).scalars().all()
            for row in rows:
                row.status = PendingApprovalStatus.expired.value
                row.decided_by = "auto"
                row.decided_at = now
                report.expired_ids.append(row.id)
            await session.commit()
        _logger.info(
            "approval_expiry_sweeper_tick",
            expired=len(report.expired_ids),
        )
        return report

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        _logger.info(
            "approval_expiry_sweeper_started",
            interval_seconds=self._interval_seconds,
        )
        while not stop_event.is_set():
            try:
                await self.run_once()
            except Exception as exc:
                _logger.exception(
                    "approval_expiry_sweeper_tick_failed", error=str(exc)
                )
            await _wait_or_stop(stop_event, self._interval_seconds)
        _logger.info("approval_expiry_sweeper_stopped")


async def _wait_or_stop(stop_event: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        return


__all__ = ["ApprovalExpirySweeper", "ExpirySweepReport"]
