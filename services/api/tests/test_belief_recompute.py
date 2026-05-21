"""Unit tests for the pure `weighted_avg_decay_v1` belief formula."""
import math
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.services.belief.recompute import (
    BELIEF_COMPUTATION_METHOD,
    DEFAULT_HALF_LIFE_DAYS,
    BeliefInput,
    weighted_avg_decay_v1,
)

_NOW = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)


def _input(
    *,
    sign: float,
    reliability: float = 1.0,
    confidence: float = 1.0,
    relevance: float = 1.0,
    age_days: float = 0.0,
    is_explicit: bool = True,
    relation_type: str = "supports_hypothesis",
) -> BeliefInput:
    return BeliefInput(
        relation_id=uuid.uuid4(),
        relation_type=relation_type,
        from_id=uuid.uuid4(),
        to_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        quote="quote",
        is_explicit=is_explicit,
        sign=sign,
        reliability=reliability,
        confidence=confidence,
        relevance=relevance,
        created_at=_NOW - timedelta(days=age_days),
    )


def test_constants_are_stable() -> None:
    assert BELIEF_COMPUTATION_METHOD == "weighted_avg_decay_v1"
    assert DEFAULT_HALF_LIFE_DAYS == 90.0


def test_empty_inputs_return_neutral_belief() -> None:
    result = weighted_avg_decay_v1([], now=_NOW)
    assert result.belief == 0.5
    assert result.contributions == []
    assert result.total_weight == 0.0
    assert result.weighted_signed_sum == 0.0
    assert result.computed_at == _NOW
    assert result.half_life_days == DEFAULT_HALF_LIFE_DAYS


def test_single_supports_pushes_belief_to_one() -> None:
    result = weighted_avg_decay_v1([_input(sign=1.0)], now=_NOW)
    assert result.belief == 1.0
    assert len(result.contributions) == 1
    contribution = result.contributions[0]
    assert contribution.sign == 1.0
    assert contribution.weight == pytest.approx(1.0)
    assert contribution.signed_contribution == pytest.approx(1.0)
    assert contribution.age_days == 0.0
    assert contribution.decay == 1.0


def test_single_contradicts_pushes_belief_to_zero() -> None:
    result = weighted_avg_decay_v1([_input(sign=-1.0)], now=_NOW)
    assert result.belief == 0.0
    contribution = result.contributions[0]
    assert contribution.sign == -1.0
    assert contribution.signed_contribution == pytest.approx(-1.0)


def test_equal_supports_and_contradicts_average_to_neutral() -> None:
    inputs = [_input(sign=1.0), _input(sign=-1.0)]
    result = weighted_avg_decay_v1(inputs, now=_NOW)
    assert result.belief == pytest.approx(0.5)
    assert result.weighted_signed_sum == pytest.approx(0.0)
    assert result.total_weight == pytest.approx(2.0)


def test_weights_combine_as_product_of_factors() -> None:
    inputs = [
        _input(sign=1.0, reliability=0.5, confidence=0.5, relevance=0.5),
    ]
    result = weighted_avg_decay_v1(inputs, now=_NOW)
    expected_weight = 0.5 * 0.5 * 0.5
    contribution = result.contributions[0]
    assert contribution.weight == pytest.approx(expected_weight)
    assert contribution.signed_contribution == pytest.approx(expected_weight)
    assert result.total_weight == pytest.approx(expected_weight)
    assert result.belief == pytest.approx(1.0)


def test_decay_applies_exponential_to_age_days() -> None:
    inputs = [_input(sign=1.0, age_days=DEFAULT_HALF_LIFE_DAYS)]
    result = weighted_avg_decay_v1(inputs, now=_NOW)
    contribution = result.contributions[0]
    assert contribution.age_days == pytest.approx(DEFAULT_HALF_LIFE_DAYS)
    assert contribution.decay == pytest.approx(math.exp(-1.0))
    assert contribution.weight == pytest.approx(math.exp(-1.0))


def test_negative_age_is_clamped_to_zero() -> None:
    future = _input(sign=1.0, age_days=-30.0)
    result = weighted_avg_decay_v1([future], now=_NOW)
    contribution = result.contributions[0]
    assert contribution.age_days == 0.0
    assert contribution.decay == 1.0


def test_half_life_parameter_changes_decay() -> None:
    inputs = [_input(sign=1.0, age_days=30.0)]
    short = weighted_avg_decay_v1(inputs, now=_NOW, half_life_days=30.0)
    long = weighted_avg_decay_v1(inputs, now=_NOW, half_life_days=180.0)
    assert short.contributions[0].decay < long.contributions[0].decay
    assert short.contributions[0].decay == pytest.approx(math.exp(-1.0))
    assert long.contributions[0].decay == pytest.approx(math.exp(-30.0 / 180.0))


def test_zero_or_negative_half_life_is_rejected() -> None:
    with pytest.raises(ValueError):
        weighted_avg_decay_v1([], now=_NOW, half_life_days=0.0)
    with pytest.raises(ValueError):
        weighted_avg_decay_v1([], now=_NOW, half_life_days=-1.0)


def test_zero_weight_inputs_collapse_to_neutral() -> None:
    inputs = [
        _input(sign=1.0, reliability=0.0),
        _input(sign=-1.0, confidence=0.0),
        _input(sign=1.0, relevance=0.0),
    ]
    result = weighted_avg_decay_v1(inputs, now=_NOW)
    assert result.belief == 0.5
    assert all(contribution.weight == 0.0 for contribution in result.contributions)


def test_higher_reliability_outweighs_older_evidence() -> None:
    high_reliability_recent = _input(sign=1.0, reliability=1.0, age_days=0.0)
    low_reliability_old = _input(sign=-1.0, reliability=0.1, age_days=180.0)
    result = weighted_avg_decay_v1(
        [high_reliability_recent, low_reliability_old], now=_NOW
    )
    assert result.belief > 0.5


def test_to_jsonable_round_trips_basic_types() -> None:
    inputs = [_input(sign=1.0, age_days=10.0)]
    result = weighted_avg_decay_v1(inputs, now=_NOW)
    payload = result.contributions[0].to_jsonable()
    assert isinstance(payload, dict)
    assert payload["sign"] == 1.0
    assert isinstance(payload["relation_id"], str)
    assert isinstance(payload["source_id"], str)
    assert payload["is_explicit"] is True
    assert payload["age_days"] == pytest.approx(10.0)


def test_belief_is_clamped_into_unit_interval_even_with_extreme_inputs() -> None:
    inputs = [
        _input(sign=1.0, reliability=10.0, confidence=10.0, relevance=10.0)
    ]
    result = weighted_avg_decay_v1(inputs, now=_NOW)
    assert 0.0 <= result.belief <= 1.0
    assert result.belief == 1.0
