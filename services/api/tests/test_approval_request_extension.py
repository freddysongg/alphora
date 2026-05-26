from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.services.approval_queue import (
    ApprovalDecision,
    ApprovalRequest,
)


def test_approval_request_carries_run_id_and_judge_verdict_id() -> None:
    run_id = uuid.uuid4()
    verdict_id = uuid.uuid4()
    request = ApprovalRequest(
        run_id=run_id,
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("1"),
        estimated_fill_price=Decimal("100"),
        mode="live",
        judge_decision="approve",
        judge_size_multiplier=None,
        judge_verdict_id=verdict_id,
    )
    assert request.run_id == run_id
    assert request.judge_verdict_id == verdict_id


def test_approval_request_judge_verdict_id_optional() -> None:
    request = ApprovalRequest(
        run_id=uuid.uuid4(),
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("1"),
        estimated_fill_price=Decimal("100"),
        mode="paper",
        judge_decision="approve",
        judge_size_multiplier=None,
        judge_verdict_id=None,
    )
    assert request.judge_verdict_id is None


def test_approval_decision_carries_pending_approval_id_and_reject_reason() -> None:
    pending_id = uuid.uuid4()
    decision = ApprovalDecision(
        decision="rejected",
        decided_by="human:default",
        decided_at=datetime.now(UTC),
        pending_approval_id=pending_id,
        reject_reason="thesis weakened",
    )
    assert decision.pending_approval_id == pending_id
    assert decision.reject_reason == "thesis weakened"


def test_approval_decision_reject_reason_defaults_to_none() -> None:
    decision = ApprovalDecision(
        decision="approved",
        decided_by="auto",
        decided_at=datetime.now(UTC),
        pending_approval_id=uuid.uuid4(),
    )
    assert decision.reject_reason is None
