"""Leakage decay + aggregate tests."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.models_evals import LeakageHoldoutCase, LeakageRun
from app.db.session import session_factory
from app.services.evals.leakage import (
    DEFAULT_DECAY_THRESHOLD,
    compute_case_decay,
    evaluate_leakage,
    persist_holdout_case,
    persist_leakage_run,
)


def _decision(
    direction: str = "overweight", conviction: float = 0.7
) -> dict[str, object]:
    return {
        "calls": [
            {
                "id": "call-1",
                "direction": direction,
                "conviction": conviction,
                "evidence_ids": ["ev-1"],
            }
        ],
        "top_quote": "q",
    }


def test_compute_case_decay_is_zero_when_decisions_match() -> None:
    decay = compute_case_decay(
        full_decision=_decision(),
        restricted_decision=_decision(),
    )
    assert pytest.approx(decay.agreement, rel=1e-9) == 1.0
    assert pytest.approx(decay.decay, rel=1e-9) == 0.0


def test_compute_case_decay_is_high_when_direction_flips() -> None:
    full = _decision(direction="overweight", conviction=0.8)
    restricted = _decision(direction="underweight", conviction=0.8)
    decay = compute_case_decay(full_decision=full, restricted_decision=restricted)
    # Direction agreement is 0 → 0.6 * 0 + 0.3 * 1.0 + 0.1 * 1.0 = 0.4 agreement.
    assert pytest.approx(decay.agreement, rel=1e-9) == 0.4
    assert pytest.approx(decay.decay, rel=1e-9) == 0.6


def test_compute_case_decay_is_zero_when_both_decisions_are_call_less() -> None:
    empty = {"calls": [], "top_quote": ""}
    decay = compute_case_decay(full_decision=empty, restricted_decision=empty)
    assert decay.agreement == 1.0
    assert decay.decay == 0.0


def test_compute_case_decay_handles_disjoint_call_sets() -> None:
    full = {
        "calls": [
            {
                "id": "call-a",
                "direction": "overweight",
                "conviction": 0.8,
                "evidence_ids": [],
            }
        ],
        "top_quote": "q",
    }
    restricted = {
        "calls": [
            {
                "id": "call-b",
                "direction": "overweight",
                "conviction": 0.8,
                "evidence_ids": [],
            }
        ],
        "top_quote": "q",
    }
    decay = compute_case_decay(full_decision=full, restricted_decision=restricted)
    assert decay.agreement == 0.0
    assert decay.decay == 1.0


def test_compute_case_decay_partial_conviction_match() -> None:
    full = _decision(direction="overweight", conviction=0.8)
    restricted = _decision(direction="overweight", conviction=0.4)
    decay = compute_case_decay(full_decision=full, restricted_decision=restricted)
    # Direction agreement 1.0, conviction agreement 1.0 - 0.4 = 0.6, set 1.0
    expected_agreement = 0.6 * 1.0 + 0.3 * 0.6 + 0.1 * 1.0
    assert pytest.approx(decay.agreement, rel=1e-9) == expected_agreement


def test_evaluate_leakage_flags_when_mean_decay_exceeds_threshold() -> None:
    outcome = evaluate_leakage([0.2, 0.5, 0.6])
    assert outcome.case_count == 3
    assert pytest.approx(outcome.mean_decay, rel=1e-9) == 1.3 / 3
    assert outcome.max_decay == 0.6
    assert outcome.threshold == DEFAULT_DECAY_THRESHOLD
    assert outcome.flagged is True


def test_evaluate_leakage_passes_when_mean_at_or_below_threshold() -> None:
    # Mean = 0.3 exactly is NOT flagged (strict >).
    outcome = evaluate_leakage([0.2, 0.3, 0.4])
    assert pytest.approx(outcome.mean_decay, rel=1e-9) == 0.3
    assert outcome.flagged is False


def test_evaluate_leakage_with_empty_input_is_not_flagged() -> None:
    outcome = evaluate_leakage([])
    assert outcome.case_count == 0
    assert outcome.flagged is False


def test_evaluate_leakage_with_high_outlier_still_uses_mean() -> None:
    outcome = evaluate_leakage([0.1, 0.1, 0.9])
    # Mean = 1.1/3 ~= 0.367 > 0.3 → flagged.
    assert outcome.flagged is True
    assert outcome.max_decay == 0.9


@pytest.mark.usefixtures("initialized_schema")
async def test_persist_holdout_case_writes_decay() -> None:
    async with session_factory() as session:
        full = _decision(direction="overweight", conviction=0.8)
        restricted = _decision(direction="underweight", conviction=0.8)
        row = await persist_holdout_case(
            session=session,
            case_name="cpi-2026-04",
            cutoff_at=datetime(2026, 4, 30, tzinfo=UTC),
            full_decision=full,
            restricted_decision=restricted,
        )
        await session.commit()
        row_id = row.id

    async with session_factory() as session:
        reloaded = (
            await session.execute(
                select(LeakageHoldoutCase).where(LeakageHoldoutCase.id == row_id)
            )
        ).scalar_one()

    assert reloaded.case_name == "cpi-2026-04"
    assert pytest.approx(reloaded.decay, rel=1e-9) == 0.6


@pytest.mark.usefixtures("initialized_schema")
async def test_persist_leakage_run_aggregates_cases() -> None:
    async with session_factory() as session:
        cases: list[LeakageHoldoutCase] = []
        for name, decay in [("a", 0.1), ("b", 0.5), ("c", 0.6)]:
            case = LeakageHoldoutCase(
                case_name=name,
                cutoff_at=datetime(2026, 4, 30, tzinfo=UTC),
                full_decision={},
                restricted_decision={},
                agreement=1.0 - decay,
                decay=decay,
            )
            session.add(case)
            cases.append(case)
        await session.commit()
        for case in cases:
            await session.refresh(case)

        row, outcome = await persist_leakage_run(
            session=session,
            run_id=None,
            cases=cases,
        )
        await session.commit()

    async with session_factory() as session:
        reloaded = (
            await session.execute(select(LeakageRun).where(LeakageRun.id == row.id))
        ).scalar_one()

    assert reloaded.case_count == 3
    assert reloaded.flagged is True
    assert outcome.flagged is True
    assert outcome.max_decay == 0.6
    assert set(reloaded.case_ids) == {str(c.id) for c in cases}
