from decimal import ROUND_HALF_UP, Decimal

from app.schemas.budget import (
    BudgetAction,
    BudgetDecision,
    BudgetThresholdName,
    BudgetThresholds,
    TokenUsage,
)
from app.services.model_pricing import get_pricing

_TOKENS_PER_MTOK: Decimal = Decimal(1_000_000)
_COST_QUANTUM: Decimal = Decimal("0.000001")
_DEFAULT_THRESHOLDS: BudgetThresholds = BudgetThresholds()


def compute_cost(usage: TokenUsage, model_id: str) -> Decimal:
    pricing = get_pricing(model_id)
    raw = (
        Decimal(usage.input_tokens) * pricing.input_per_mtok
        + Decimal(usage.output_tokens) * pricing.output_per_mtok
        + Decimal(usage.cached_input_tokens) * pricing.cached_input_per_mtok
        + Decimal(usage.reasoning_tokens) * pricing.reasoning_per_mtok
    ) / _TOKENS_PER_MTOK
    return raw.quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)


class BudgetGuard:
    def __init__(self, thresholds: BudgetThresholds = _DEFAULT_THRESHOLDS) -> None:
        self._thresholds = thresholds

    @property
    def thresholds(self) -> BudgetThresholds:
        return self._thresholds

    def evaluate(self, *, run_cost_usd: Decimal, daily_cost_usd: Decimal) -> BudgetDecision:
        if daily_cost_usd >= self._thresholds.daily_usd:
            return BudgetDecision(
                action=BudgetAction.kill,
                reason=(
                    f"daily budget exceeded: ${daily_cost_usd} >= ${self._thresholds.daily_usd}"
                ),
                run_cost_usd=run_cost_usd,
                daily_cost_usd=daily_cost_usd,
                threshold_crossed=BudgetThresholdName.daily,
            )
        if run_cost_usd >= self._thresholds.catastrophic_run_usd:
            return BudgetDecision(
                action=BudgetAction.kill,
                reason=(
                    f"run budget catastrophic: ${run_cost_usd} "
                    f">= ${self._thresholds.catastrophic_run_usd}"
                ),
                run_cost_usd=run_cost_usd,
                daily_cost_usd=daily_cost_usd,
                threshold_crossed=BudgetThresholdName.catastrophic_run,
            )
        if run_cost_usd >= self._thresholds.hard_run_usd:
            return BudgetDecision(
                action=BudgetAction.pause,
                reason=(
                    f"run budget hard limit reached: ${run_cost_usd} "
                    f">= ${self._thresholds.hard_run_usd}"
                ),
                run_cost_usd=run_cost_usd,
                daily_cost_usd=daily_cost_usd,
                threshold_crossed=BudgetThresholdName.hard_run,
            )
        if run_cost_usd >= self._thresholds.soft_run_usd:
            return BudgetDecision(
                action=BudgetAction.warn,
                reason=(
                    f"run budget soft limit reached: ${run_cost_usd} "
                    f">= ${self._thresholds.soft_run_usd}"
                ),
                run_cost_usd=run_cost_usd,
                daily_cost_usd=daily_cost_usd,
                threshold_crossed=BudgetThresholdName.soft_run,
            )
        return BudgetDecision(
            action=BudgetAction.allow,
            reason=None,
            run_cost_usd=run_cost_usd,
            daily_cost_usd=daily_cost_usd,
            threshold_crossed=None,
        )
