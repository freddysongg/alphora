from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.approval_queue import (
    ApprovalDecision,
    ApprovalRequest,
    request_approval,
)


@pytest.mark.asyncio
async def test_live_request_raises_not_implemented(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Live approval queue (Task 6) is not yet implemented; raises fast."""
    req = ApprovalRequest(
        run_id=uuid.uuid4(),
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("1"),
        estimated_fill_price=Decimal("500"),
        mode="live",
        judge_decision="approve",
        judge_size_multiplier=None,
        judge_verdict_id=None,
    )
    with pytest.raises(NotImplementedError) as exc_info:
        await request_approval(req, session_maker=session_maker)
    assert "phase 7" in str(exc_info.value).lower()


def test_approval_decision_carries_decided_by_and_decided_at() -> None:
    from datetime import UTC, datetime

    d = ApprovalDecision(
        decision="approved",
        decided_by="auto",
        decided_at=datetime(2026, 6, 15, 13, 30, tzinfo=UTC),
        pending_approval_id=uuid.uuid4(),
    )
    assert d.decision == "approved"
    assert d.decided_by == "auto"
