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


class LlmBudgetActionEnum(StrEnum):
    allow = "allow"
    warn = "warn"
    pause = "pause"
    kill = "kill"


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
    prompt_version: str | None
    stage: str | None
    agent_name: str | None
    call_index: int | None
    temperature: float | None
    seed: int | None
    reasoning_effort: str | None
    input_payload: dict[str, object] | None
    output_content: str | None
    budget_action: LlmBudgetActionEnum | None
    created_at: datetime


class LlmCallReplayPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_log_id: uuid.UUID
    model: str
    prompt_version: str | None
    input_payload: dict[str, object]
    output_content: str | None
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    reasoning_tokens: int
    cost_usd: Decimal
    latency_ms: int
    status: LlmCallStatusEnum
    error_message: str | None
    replayed_at: datetime


__all__ = [
    "LlmBudgetActionEnum",
    "LlmCallLogPublic",
    "LlmCallReplayPublic",
    "LlmCallStatusEnum",
]
