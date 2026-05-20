"""Pre-flight run cost estimator.

Aggregates historical `llm_call_logs` by stage to estimate the cost of a
not-yet-started run. The estimator joins llm logs against `research_runs` to
filter by strategy, computes mean/p95 cost per stage from successful and
warned runs (skipping budget_paused/budget_killed/error rows that do not
reflect a healthy stage cost), then sums the per-stage means / p95s into a
total estimate. Stage list comes from `STAGE_SCHEMES`. Stages without any
historical observations contribute zero.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_runs import ResearchRun
from app.schemas.common import StrategyEnum
from app.schemas.cost_estimate import RunCostEstimate, StageCostEstimate

_HEALTHY_STATUSES: frozenset[LlmCallStatus] = frozenset({LlmCallStatus.success})
_STRATEGY_STAGE_MAP: dict[str, tuple[str, ...]] = {
    "funnel_research": (
        "macro_synthesis",
        "judge",
        "extraction",
        "sector_synthesis",
        "company_synthesis",
        "hypothesis_dedup",
    ),
}


def _percentile(values: list[Decimal], p: float) -> Decimal:
    if not values:
        return Decimal("0")
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = p * (len(sorted_values) - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    weight = Decimal(str(rank - lower_index))
    lower = sorted_values[lower_index]
    upper = sorted_values[upper_index]
    return lower + (upper - lower) * weight


async def estimate_run_cost(
    *,
    session: AsyncSession,
    strategy: StrategyEnum,
) -> RunCostEstimate:
    """Aggregate historical per-stage costs from `llm_call_logs`.

    Returns a `RunCostEstimate` for `strategy` whose `stages` list is the
    canonical stage order for the strategy. Each row carries mean / p95 cost
    and token usage across all healthy historical calls at that stage; the
    top-level `estimated_total_usd` and `estimated_p95_usd` sum the per-stage
    figures. Sample size is the count of contributing log rows for the stage;
    `sample_run_count` is the number of distinct runs across the strategy.
    """
    stmt = (
        select(
            LlmCallLog.stage,
            LlmCallLog.run_id,
            LlmCallLog.cost_usd,
            LlmCallLog.input_tokens,
            LlmCallLog.cached_input_tokens,
        )
        .join(ResearchRun, ResearchRun.id == LlmCallLog.run_id)
        .where(
            ResearchRun.strategy == strategy.value,
            LlmCallLog.status.in_([s.value for s in _HEALTHY_STATUSES]),
            LlmCallLog.stage.is_not(None),
        )
    )
    rows = (await session.execute(stmt)).all()

    by_stage: dict[str, list[tuple[Decimal, int, int]]] = {}
    distinct_runs: set[object] = set()
    for stage, run_id, cost, input_tokens, cached_input_tokens in rows:
        if stage is None:
            continue
        by_stage.setdefault(stage, []).append(
            (Decimal(str(cost)), int(input_tokens or 0), int(cached_input_tokens or 0))
        )
        distinct_runs.add(run_id)

    canonical_stages = _STRATEGY_STAGE_MAP.get(strategy.value, ())
    observed_stages = list(by_stage.keys())
    # Preserve canonical order, then append any other observed stages.
    ordered_stages = list(canonical_stages) + [
        s for s in observed_stages if s not in canonical_stages
    ]

    stage_estimates: list[StageCostEstimate] = []
    total = Decimal("0")
    total_p95 = Decimal("0")
    for stage in ordered_stages:
        bucket = by_stage.get(stage, [])
        costs = [row[0] for row in bucket]
        if not costs:
            stage_estimates.append(
                StageCostEstimate(
                    stage=stage,
                    sample_size=0,
                    mean_cost_usd=Decimal("0"),
                    p95_cost_usd=Decimal("0"),
                    mean_input_tokens=0.0,
                    mean_cached_input_tokens=0.0,
                )
            )
            continue
        mean_cost = sum(costs, Decimal("0")) / Decimal(len(costs))
        p95_cost = _percentile(costs, 0.95)
        mean_input_tokens = sum(row[1] for row in bucket) / len(bucket)
        mean_cached_input_tokens = sum(row[2] for row in bucket) / len(bucket)
        stage_estimates.append(
            StageCostEstimate(
                stage=stage,
                sample_size=len(bucket),
                mean_cost_usd=mean_cost.quantize(Decimal("0.000001")),
                p95_cost_usd=p95_cost.quantize(Decimal("0.000001")),
                mean_input_tokens=mean_input_tokens,
                mean_cached_input_tokens=mean_cached_input_tokens,
            )
        )
        total = total + mean_cost
        total_p95 = total_p95 + p95_cost

    return RunCostEstimate(
        strategy=strategy,
        sample_run_count=len(distinct_runs),
        estimated_total_usd=total.quantize(Decimal("0.000001")),
        estimated_p95_usd=total_p95.quantize(Decimal("0.000001")),
        stages=stage_estimates,
    )


__all__ = ["estimate_run_cost"]
