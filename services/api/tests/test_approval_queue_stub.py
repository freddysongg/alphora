from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.approval_queue import (
    ApprovalDecision,
    ApprovalRequest,
    request_approval,
)


def _paper_request() -> ApprovalRequest:
    return ApprovalRequest(
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("1"),
        estimated_fill_price=Decimal("500"),
        mode="paper",
        judge_decision="approve",
        judge_size_multiplier=None,
    )


@pytest.mark.asyncio
async def test_paper_auto_approves_immediately() -> None:
    decision = await request_approval(_paper_request())
    assert isinstance(decision, ApprovalDecision)
    assert decision.decision == "approved"
    assert decision.decided_by == "auto"
    assert decision.decided_at is not None


@pytest.mark.asyncio
async def test_paper_auto_approves_even_when_judge_returned_veto() -> None:
    """Per spec §4.6: in paper mode the judge is advisory — veto does NOT
    block. The approval queue auto-approves regardless of the judge."""
    req = ApprovalRequest(
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("1"),
        estimated_fill_price=Decimal("500"),
        mode="paper",
        judge_decision="veto",
        judge_size_multiplier=None,
    )
    decision = await request_approval(req)
    assert decision.decision == "approved"


@pytest.mark.asyncio
async def test_live_request_raises_not_implemented_in_stub() -> None:
    """Phase 7 implements the live branch (wait for human). The Phase 4
    stub explicitly refuses live requests so paper-only callers don't
    accidentally use this stub in live mode."""
    req = ApprovalRequest(
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("1"),
        estimated_fill_price=Decimal("500"),
        mode="live",
        judge_decision="approve",
        judge_size_multiplier=None,
    )
    with pytest.raises(NotImplementedError) as exc_info:
        await request_approval(req)
    assert "phase 7" in str(exc_info.value).lower()


def test_approval_decision_carries_decided_by_and_decided_at() -> None:
    from datetime import UTC, datetime
    d = ApprovalDecision(
        decision="approved",
        decided_by="auto",
        decided_at=datetime(2026, 6, 15, 13, 30, tzinfo=UTC),
    )
    assert d.decision == "approved"
    assert d.decided_by == "auto"
