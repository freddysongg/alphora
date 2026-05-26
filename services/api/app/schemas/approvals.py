"""Pydantic schemas for the Phase 7 HITL approval queue API."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ApprovalStatusLiteral = Literal["pending", "approved", "rejected", "expired"]
ApprovalModeLiteral = Literal["paper", "live"]
ApprovalSideLiteral = Literal["buy", "sell"]


class PendingApprovalPublic(BaseModel):
    """List-view projection. Excludes the verdict context payload."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    judge_verdict_id: uuid.UUID | None
    strategy_key: str
    ticker: str
    side: ApprovalSideLiteral
    qty: Decimal
    estimated_fill_price: Decimal
    mode: ApprovalModeLiteral
    status: ApprovalStatusLiteral
    decided_by: str | None
    decided_at: datetime | None
    reject_reason: str | None
    expires_at: datetime | None
    created_at: datetime


class JudgeVerdictSummary(BaseModel):
    """Embedded inside PendingApprovalDetail when a verdict link exists."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    decision: str
    size_multiplier: float | None
    reasoning_md: str
    context_payload: dict[str, object]
    llm_model: str | None
    prompt_version: str | None
    bar_ts: datetime


class PendingApprovalDetail(PendingApprovalPublic):
    """Detail view. Embeds the linked judge verdict when present."""

    judge_verdict: JudgeVerdictSummary | None


class ApprovalRejectPayload(BaseModel):
    reject_reason: str | None = Field(default=None, max_length=512)
