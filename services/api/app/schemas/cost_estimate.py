from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.common import StrategyEnum


class StageCostEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: str
    sample_size: int
    mean_cost_usd: Decimal
    p95_cost_usd: Decimal
    mean_input_tokens: float
    mean_cached_input_tokens: float


class RunCostEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: StrategyEnum
    sample_run_count: int
    estimated_total_usd: Decimal
    estimated_p95_usd: Decimal
    stages: list[StageCostEstimate]


__all__ = ["RunCostEstimate", "StageCostEstimate"]
