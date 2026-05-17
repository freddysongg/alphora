from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)


class BudgetThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    soft_run_usd: Decimal = Decimal("5.00")
    hard_run_usd: Decimal = Decimal("20.00")
    catastrophic_run_usd: Decimal = Decimal("100.00")
    daily_usd: Decimal = Decimal("500.00")


class BudgetAction(StrEnum):
    allow = "allow"
    warn = "warn"
    pause = "pause"
    kill = "kill"


class BudgetDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: BudgetAction
    reason: str | None
    run_cost_usd: Decimal
    daily_cost_usd: Decimal
    threshold_crossed: str | None


class BudgetSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID | None
    run_cost_usd: Decimal
    daily_cost_usd: Decimal
    thresholds: BudgetThresholds
    last_decision: BudgetDecision | None
