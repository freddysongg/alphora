from __future__ import annotations

import uuid

from app.services.approval_queue import (
    ApprovalDecision,
)


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
