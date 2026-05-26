"""SQLAlchemy model for the Phase 7 HITL approval queue (spec §11.1).

`pending_approvals` is one row per order request — paper and live both
land here. Paper rows are inserted with `status="approved"` (or briefly
"pending" when an auto-approve delay is configured). Live rows wait for a
human to POST to `/api/approvals/{id}/approve` or for the expiry sweeper
to flip them to `expired`.

The FK to `judge_verdicts.id` is SET NULL — Phase 9 may admin-delete a
verdict row without nuking its corresponding approval audit. The FK to
`strategy_runs.id` is CASCADE — when a run is deleted, its approval
history goes with it.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PendingApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


class PendingApprovalRow(Base):
    __tablename__ = "pending_approvals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("strategy_runs.id", ondelete="CASCADE"), nullable=False
    )
    judge_verdict_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("judge_verdicts.id", ondelete="SET NULL"), nullable=True
    )
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    estimated_fill_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_pending_approvals_run_status",
            "run_id",
            "status",
        ),
        Index(
            "ix_pending_approvals_status_expires",
            "status",
            "expires_at",
        ),
    )


__all__ = [
    "PendingApprovalRow",
    "PendingApprovalStatus",
]
