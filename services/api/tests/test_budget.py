from decimal import Decimal

import pytest

from app.schemas.budget import BudgetAction, TokenUsage
from app.services.budget import BudgetGuard, compute_cost
from app.services.model_pricing import UnknownModelError


def test_compute_cost_basic_input_output_only() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=500_000)
    cost = compute_cost(usage, "gpt-5")
    assert cost == Decimal("6.250000")


def test_compute_cost_all_token_types() -> None:
    usage = TokenUsage(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cached_input_tokens=2_000_000,
        reasoning_tokens=500_000,
    )
    cost = compute_cost(usage, "gpt-5")
    expected = (
        Decimal("1.25")
        + Decimal("10.00")
        + Decimal("2") * Decimal("0.125")
        + Decimal("0.5") * Decimal("10.00")
    ).quantize(Decimal("0.000001"))
    assert cost == expected


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
    assert decision.threshold_crossed == "soft_run"


def test_evaluate_pause_at_hard_threshold() -> None:
    guard = BudgetGuard()
    decision = guard.evaluate(run_cost_usd=Decimal("20.00"), daily_cost_usd=Decimal("20.00"))
    assert decision.action is BudgetAction.pause
    assert decision.threshold_crossed == "hard_run"


def test_evaluate_kill_at_catastrophic_run_threshold() -> None:
    guard = BudgetGuard()
    decision = guard.evaluate(run_cost_usd=Decimal("100.00"), daily_cost_usd=Decimal("100.00"))
    assert decision.action is BudgetAction.kill
    assert decision.threshold_crossed == "catastrophic_run"


def test_evaluate_kill_at_daily_threshold() -> None:
    guard = BudgetGuard()
    decision = guard.evaluate(run_cost_usd=Decimal("1.00"), daily_cost_usd=Decimal("500.00"))
    assert decision.action is BudgetAction.kill
    assert decision.threshold_crossed == "daily"


def test_evaluate_priority_daily_beats_run_thresholds() -> None:
    guard = BudgetGuard()
    decision = guard.evaluate(run_cost_usd=Decimal("50.00"), daily_cost_usd=Decimal("500.00"))
    assert decision.action is BudgetAction.kill
    assert decision.threshold_crossed == "daily"


def test_evaluate_priority_catastrophic_beats_pause() -> None:
    guard = BudgetGuard()
    decision = guard.evaluate(run_cost_usd=Decimal("100.00"), daily_cost_usd=Decimal("10.00"))
    assert decision.action is BudgetAction.kill
    assert decision.threshold_crossed == "catastrophic_run"


def test_evaluate_priority_pause_beats_warn() -> None:
    guard = BudgetGuard()
    decision = guard.evaluate(run_cost_usd=Decimal("20.00"), daily_cost_usd=Decimal("10.00"))
    assert decision.action is BudgetAction.pause
    assert decision.threshold_crossed == "hard_run"
