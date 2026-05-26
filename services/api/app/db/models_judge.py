"""SQLAlchemy model for Phase 6 judge verdicts (spec §11.1).

`judge_verdicts` stores every LLM-judge verdict — including conservative-
default vetoes triggered by sparse context, LLM transport errors, malformed
JSON responses, or budget exceptions. Foreign-keys to `strategy_runs.id`
(CASCADE on run delete) and optionally to `llm_call_logs.id` (SET NULL when
the originating LLM call row is deleted or when no LLM call was made for
this verdict).

This file is its own module (rather than appended to
`models_strategy_runner.py`) because the table's lifecycle is logically
distinct from the runner's own tables: the verdict is a queryable artifact
that Phase 9 dashboards project independently of the runner's per-bar event
log. Co-locating it with the runner tables would imply a tighter coupling
than actually exists.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
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


class JudgeDecisionDb(StrEnum):
    approve = "approve"
    veto = "veto"
    approve_reduced = "approve_reduced"


class JudgeVerdictRow(Base):
    __tablename__ = "judge_verdicts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("strategy_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    bar_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    proposed_qty: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    size_multiplier: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning_md: Mapped[str] = mapped_column(Text, nullable=False)
    context_payload: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    llm_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    llm_call_log_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("llm_call_logs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_judge_verdicts_run_id", "run_id"),
        Index("ix_judge_verdicts_decision", "decision"),
        Index("ix_judge_verdicts_bar_ts", "bar_ts"),
    )


__all__ = ["JudgeDecisionDb", "JudgeVerdictRow"]
