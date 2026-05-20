from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.budget import BudgetAction, BudgetThresholdName, BudgetThresholds, TokenUsage
from app.services.budget import BudgetGuard, compute_cost
from app.services.model_pricing import UnknownModelError


def test_compute_cost_basic_input_output_only() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=500_000)
    cost = compute_cost(usage, "gpt-5")
    assert cost == Decimal("6.250000")


def test_compute_cost_all_token_types() -> None:
    usage = TokenUsage(
        input_tokens=1000,
        output_tokens=500,
        cached_input_tokens=200,
        reasoning_tokens=100,
    )
    cost = compute_cost(usage, "gpt-5")
    expected = (
        Decimal("800") * Decimal("1.25")
        + Decimal("200") * Decimal("0.125")
        + Decimal("400") * Decimal("10.00")
        + Decimal("100") * Decimal("10.00")
    ) / Decimal(1_000_000)
    expected = expected.quantize(Decimal("0.000001"))
    assert cost == expected


def test_compute_cost_cached_tokens_priced_at_cached_rate() -> None:
    usage = TokenUsage(input_tokens=1000, cached_input_tokens=1000)
    cost = compute_cost(usage, "gpt-5")
    assert cost == Decimal("0.000125")


def test_compute_cost_reasoning_tokens_priced_at_reasoning_rate() -> None:
    usage = TokenUsage(output_tokens=1000, reasoning_tokens=1000)
    cost = compute_cost(usage, "gpt-5")
    assert cost == Decimal("0.010000")


def test_compute_cost_zero_usage_returns_zero() -> None:
    cost = compute_cost(TokenUsage(), "gpt-5")
    assert cost == Decimal("0.000000")


def test_compute_cost_unknown_model_raises() -> None:
    with pytest.raises(UnknownModelError):
        compute_cost(TokenUsage(input_tokens=1), "no-such-model")


def test_compute_cost_returns_quantized_decimal() -> None:
    usage = TokenUsage(input_tokens=1)
    cost = compute_cost(usage, "gpt-5")
    assert cost.as_tuple().exponent == -6


def test_evaluate_allow_when_well_under_limits() -> None:
    guard = BudgetGuard()
    decision = guard.evaluate(run_cost_usd=Decimal("0.50"), daily_cost_usd=Decimal("1.00"))
    assert decision.action is BudgetAction.allow
    assert decision.reason is None
    assert decision.threshold_crossed is None
    assert decision.run_cost_usd == Decimal("0.50")
    assert decision.daily_cost_usd == Decimal("1.00")


def test_evaluate_warn_at_soft_threshold() -> None:
    guard = BudgetGuard()
    decision = guard.evaluate(run_cost_usd=Decimal("5.00"), daily_cost_usd=Decimal("5.00"))
    assert decision.action is BudgetAction.warn
    assert decision.threshold_crossed is BudgetThresholdName.soft_run


def test_evaluate_pause_at_hard_threshold() -> None:
    guard = BudgetGuard()
    decision = guard.evaluate(run_cost_usd=Decimal("20.00"), daily_cost_usd=Decimal("20.00"))
    assert decision.action is BudgetAction.pause
    assert decision.threshold_crossed is BudgetThresholdName.hard_run


def test_evaluate_kill_at_catastrophic_run_threshold() -> None:
    guard = BudgetGuard()
    decision = guard.evaluate(run_cost_usd=Decimal("100.00"), daily_cost_usd=Decimal("100.00"))
    assert decision.action is BudgetAction.kill
    assert decision.threshold_crossed is BudgetThresholdName.catastrophic_run


def test_evaluate_kill_at_daily_threshold() -> None:
    guard = BudgetGuard()
    decision = guard.evaluate(run_cost_usd=Decimal("1.00"), daily_cost_usd=Decimal("500.00"))
    assert decision.action is BudgetAction.kill
    assert decision.threshold_crossed is BudgetThresholdName.daily


def test_evaluate_priority_daily_beats_run_thresholds() -> None:
    guard = BudgetGuard()
    decision = guard.evaluate(run_cost_usd=Decimal("50.00"), daily_cost_usd=Decimal("500.00"))
    assert decision.action is BudgetAction.kill
    assert decision.threshold_crossed is BudgetThresholdName.daily


def test_evaluate_priority_catastrophic_beats_pause() -> None:
    guard = BudgetGuard()
    decision = guard.evaluate(run_cost_usd=Decimal("100.00"), daily_cost_usd=Decimal("10.00"))
    assert decision.action is BudgetAction.kill
    assert decision.threshold_crossed is BudgetThresholdName.catastrophic_run


def test_evaluate_priority_pause_beats_warn() -> None:
    guard = BudgetGuard()
    decision = guard.evaluate(run_cost_usd=Decimal("20.00"), daily_cost_usd=Decimal("10.00"))
    assert decision.action is BudgetAction.pause
    assert decision.threshold_crossed is BudgetThresholdName.hard_run


def test_budget_thresholds_is_immutable() -> None:
    t = BudgetThresholds()
    with pytest.raises(ValidationError):
        t.soft_run_usd = Decimal("999")


def test_evaluate_per_stage_cap_triggers_pause_under_run_thresholds() -> None:
    thresholds = BudgetThresholds(
        soft_run_usd=Decimal("5.00"),
        hard_run_usd=Decimal("20.00"),
        catastrophic_run_usd=Decimal("100.00"),
        daily_usd=Decimal("500.00"),
        per_stage_usd={"sector_synthesis": Decimal("1.00")},
    )
    guard = BudgetGuard(thresholds)
    decision = guard.evaluate(
        run_cost_usd=Decimal("2.00"),
        daily_cost_usd=Decimal("2.00"),
        stage="sector_synthesis",
        stage_cost_usd=Decimal("1.00"),
    )
    assert decision.action is BudgetAction.pause
    assert decision.threshold_crossed is BudgetThresholdName.per_stage
    assert decision.reason is not None
    assert "sector_synthesis" in decision.reason


def test_evaluate_per_stage_cap_no_op_below_cap() -> None:
    thresholds = BudgetThresholds(
        per_stage_usd={"macro_synthesis": Decimal("5.00")},
    )
    guard = BudgetGuard(thresholds)
    decision = guard.evaluate(
        run_cost_usd=Decimal("0.50"),
        daily_cost_usd=Decimal("0.50"),
        stage="macro_synthesis",
        stage_cost_usd=Decimal("4.99"),
    )
    assert decision.action is BudgetAction.allow
    assert decision.threshold_crossed is None


def test_evaluate_per_stage_cap_ignored_when_stage_unknown_to_caps() -> None:
    thresholds = BudgetThresholds(
        per_stage_usd={"some_other_stage": Decimal("0.01")},
    )
    guard = BudgetGuard(thresholds)
    decision = guard.evaluate(
        run_cost_usd=Decimal("0.5"),
        daily_cost_usd=Decimal("0.5"),
        stage="unknown_stage",
        stage_cost_usd=Decimal("100.00"),
    )
    assert decision.action is BudgetAction.allow


def test_evaluate_per_stage_cap_ignored_when_no_stage_passed() -> None:
    thresholds = BudgetThresholds(
        per_stage_usd={"sector_synthesis": Decimal("0.01")},
    )
    guard = BudgetGuard(thresholds)
    decision = guard.evaluate(
        run_cost_usd=Decimal("1.0"),
        daily_cost_usd=Decimal("1.0"),
    )
    assert decision.action is BudgetAction.allow


def test_evaluate_daily_kill_beats_per_stage_pause() -> None:
    """Daily kill must outrank the per-stage pause."""
    thresholds = BudgetThresholds(
        per_stage_usd={"x": Decimal("0.01")},
    )
    guard = BudgetGuard(thresholds)
    decision = guard.evaluate(
        run_cost_usd=Decimal("1.0"),
        daily_cost_usd=Decimal("500.00"),
        stage="x",
        stage_cost_usd=Decimal("1.00"),
    )
    assert decision.action is BudgetAction.kill
    assert decision.threshold_crossed is BudgetThresholdName.daily


def test_evaluate_catastrophic_kill_beats_per_stage_pause() -> None:
    thresholds = BudgetThresholds(
        per_stage_usd={"x": Decimal("0.01")},
    )
    guard = BudgetGuard(thresholds)
    decision = guard.evaluate(
        run_cost_usd=Decimal("100.00"),
        daily_cost_usd=Decimal("100.00"),
        stage="x",
        stage_cost_usd=Decimal("1.00"),
    )
    assert decision.action is BudgetAction.kill
    assert decision.threshold_crossed is BudgetThresholdName.catastrophic_run
