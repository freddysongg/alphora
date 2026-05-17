import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class LlmCallStatusEnum(StrEnum):
    success = "success"
    error = "error"
    budget_paused = "budget_paused"
    budget_killed = "budget_killed"


class LlmCallLogPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID | None
    model: str
    prompt_hash: str
    input_hash: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    reasoning_tokens: int
    cost_usd: Decimal
    latency_ms: int
    status: LlmCallStatusEnum
    error_message: str | None
    evidence_ids: list[str] | None
    created_at: datetime


__all__ = ["LlmCallLogPublic", "LlmCallStatusEnum"]
