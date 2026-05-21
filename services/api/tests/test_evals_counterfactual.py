"""Deterministic fixture, rejection-gate, and persistence tests for the
counterfactual harness.
"""

import pytest

from app.db.models_evals import (
    BriefKind,
    CounterfactualGateRun,
    CounterfactualPerturbation,
    PerturbationKind,
)
from app.db.models_runs import ResearchRun, RunStatus
from app.db.session import session_factory
from app.services.evals.counterfactual import (
    DEFAULT_CHANGE_RATE_THRESHOLD,
    CounterfactualResult,
    decision_delta,
    decisions_changed,
    evaluate_gate,
    generate_perturbations,
    operators,
    persist_counterfactual_gate,
)


def _base_decision() -> dict[str, object]:
    return {
        "calls": [
            {
                "id": "call-1",
                "direction": "overweight",
                "conviction": 0.8,
                "evidence_ids": ["ev-1", "ev-2"],
            },
            {
                "id": "call-2",
                "direction": "underweight",
                "conviction": 0.6,
                "evidence_ids": ["ev-3"],
            },
        ],
        "top_quote": "the most cited quote",
    }


def test_operators_catalogue_is_deterministic_and_complete() -> None:
    kinds = [op.kind for op in operators()]
    assert kinds == [
        PerturbationKind.drop_top_evidence,
        PerturbationKind.flip_top_call_direction,
        PerturbationKind.redact_top_quote,
        PerturbationKind.lower_top_call_conviction,
        PerturbationKind.swap_call_ordering,
    ]
    meaningful_kinds = {op.kind for op in operators() if op.is_meaningful}
    assert PerturbationKind.swap_call_ordering not in meaningful_kinds
    assert PerturbationKind.flip_top_call_direction in meaningful_kinds


def test_flip_top_call_direction_produces_direction_change() -> None:
    baseline = _base_decision()
    results = generate_perturbations(baseline)
    flip = next(r for r in results if r.kind is PerturbationKind.flip_top_call_direction)
    assert flip.decision_changed is True
    delta = flip.decision_delta
    direction_changes = delta["direction_changes"]
    assert isinstance(direction_changes, list)
    assert len(direction_changes) == 1
    first_change = direction_changes[0]
    assert isinstance(first_change, dict)
    assert first_change["id"] == "call-1"
    assert first_change["from"] == "overweight"
    assert first_change["to"] == "underweight"


def test_drop_top_evidence_removes_one_evidence_and_changes_decision() -> None:
    baseline = _base_decision()
    results = generate_perturbations(baseline)
    drop = next(r for r in results if r.kind is PerturbationKind.drop_top_evidence)
    assert drop.perturbation_input["removed_evidence_id"] == "ev-1"
    # call-1 still has ev-2, so its direction and conviction are preserved by
    # the deterministic operator. The decision delta should NOT register a
    # direction change.
    direction_changes = drop.decision_delta["direction_changes"]
    assert direction_changes == []


def test_lower_top_call_conviction_drops_call_conviction_by_floor_delta() -> None:
    baseline = _base_decision()
    results = generate_perturbations(baseline)
    lowered = next(
        r for r in results if r.kind is PerturbationKind.lower_top_call_conviction
    )
    perturbed_calls = lowered.perturbed_output["calls"]
    assert isinstance(perturbed_calls, list)
    first = perturbed_calls[0]
    assert isinstance(first, dict)
    new_conviction = first["conviction"]
    assert isinstance(new_conviction, float)
    assert pytest.approx(new_conviction, rel=1e-9) == 0.4
    assert lowered.decision_changed is True


def test_swap_call_ordering_changes_order_but_not_decision() -> None:
    baseline = _base_decision()
    results = generate_perturbations(baseline)
    swap = next(r for r in results if r.kind is PerturbationKind.swap_call_ordering)
    assert swap.decision_delta["order_changed"] is True
    assert swap.decision_changed is False  # marginal-only signal
    assert swap.is_meaningful is False


def test_redact_top_quote_marks_quote_changed_but_not_decision() -> None:
    baseline = _base_decision()
    results = generate_perturbations(baseline)
    redact = next(r for r in results if r.kind is PerturbationKind.redact_top_quote)
    assert redact.perturbed_output["top_quote"] == ""
    assert redact.decision_delta["quote_changed"] is True
    assert redact.decision_changed is False


def test_decision_delta_detects_added_and_removed_calls() -> None:
    baseline = _base_decision()
    perturbed = {
        "calls": [
            {
                "id": "call-1",
                "direction": "overweight",
                "conviction": 0.8,
                "evidence_ids": ["ev-1"],
            },
            {
                "id": "call-99",
                "direction": "neutral",
                "conviction": 0.1,
                "evidence_ids": [],
            },
        ],
        "top_quote": "the most cited quote",
    }
    delta = decision_delta(baseline, perturbed)
    assert delta["added_call_ids"] == ["call-99"]
    assert delta["removed_call_ids"] == ["call-2"]
    assert decisions_changed(delta) is True


def test_evaluate_gate_passes_when_at_least_half_of_meaningful_change() -> None:
    results = [
        CounterfactualResult(
            kind=PerturbationKind.drop_top_evidence,
            is_meaningful=True,
            perturbation_input={},
            baseline_output={},
            perturbed_output={},
            decision_delta={},
            decision_changed=True,
        ),
        CounterfactualResult(
            kind=PerturbationKind.flip_top_call_direction,
            is_meaningful=True,
            perturbation_input={},
            baseline_output={},
            perturbed_output={},
            decision_delta={},
            decision_changed=True,
        ),
        CounterfactualResult(
            kind=PerturbationKind.lower_top_call_conviction,
            is_meaningful=True,
            perturbation_input={},
            baseline_output={},
            perturbed_output={},
            decision_delta={},
            decision_changed=False,
        ),
        CounterfactualResult(
            kind=PerturbationKind.swap_call_ordering,
            is_meaningful=False,
            perturbation_input={},
            baseline_output={},
            perturbed_output={},
            decision_delta={},
            decision_changed=False,
        ),
    ]
    outcome = evaluate_gate(results)
    assert outcome.perturbation_count == 4
    assert outcome.meaningful_count == 3
    assert outcome.meaningful_changed_count == 2
    assert pytest.approx(outcome.change_rate, rel=1e-9) == 2 / 3
    assert outcome.threshold == DEFAULT_CHANGE_RATE_THRESHOLD
    assert outcome.passed is True


def test_evaluate_gate_fails_when_below_threshold() -> None:
    results = [
        CounterfactualResult(
            kind=PerturbationKind.drop_top_evidence,
            is_meaningful=True,
            perturbation_input={},
            baseline_output={},
            perturbed_output={},
            decision_delta={},
            decision_changed=False,
        ),
        CounterfactualResult(
            kind=PerturbationKind.flip_top_call_direction,
            is_meaningful=True,
            perturbation_input={},
            baseline_output={},
            perturbed_output={},
            decision_delta={},
            decision_changed=True,
        ),
        CounterfactualResult(
            kind=PerturbationKind.lower_top_call_conviction,
            is_meaningful=True,
            perturbation_input={},
            baseline_output={},
            perturbed_output={},
            decision_delta={},
            decision_changed=False,
        ),
    ]
    outcome = evaluate_gate(results)
    assert outcome.meaningful_count == 3
    assert outcome.meaningful_changed_count == 1
    assert pytest.approx(outcome.change_rate, rel=1e-9) == 1 / 3
    assert outcome.passed is False


def test_evaluate_gate_threshold_boundary_is_inclusive() -> None:
    # Exactly 50% of meaningful perturbations change → passes (>= threshold).
    results = [
        CounterfactualResult(
            kind=PerturbationKind.drop_top_evidence,
            is_meaningful=True,
            perturbation_input={},
            baseline_output={},
            perturbed_output={},
            decision_delta={},
            decision_changed=True,
        ),
        CounterfactualResult(
            kind=PerturbationKind.flip_top_call_direction,
            is_meaningful=True,
            perturbation_input={},
            baseline_output={},
            perturbed_output={},
            decision_delta={},
            decision_changed=False,
        ),
    ]
    outcome = evaluate_gate(results)
    assert pytest.approx(outcome.change_rate, rel=1e-9) == 0.5
    assert outcome.passed is True


def test_evaluate_gate_passes_vacuously_when_no_meaningful_perturbations() -> None:
    outcome = evaluate_gate([])
    assert outcome.passed is True
    assert outcome.meaningful_count == 0
    assert outcome.change_rate == 0.0


def test_generate_perturbations_demotes_meaningful_for_empty_baseline() -> None:
    """Empty briefs make every top-call operator a no-op — none of those
    should count as meaningful, so the gate must pass vacuously instead of
    failing because nothing changed.
    """
    empty = {"calls": [], "top_quote": ""}
    results = generate_perturbations(empty)
    assert all(not r.is_meaningful for r in results), (
        "no-op perturbations on an empty baseline must not be flagged as meaningful"
    )
    outcome = evaluate_gate(results)
    assert outcome.meaningful_count == 0
    assert outcome.passed is True


def test_generate_perturbations_demotes_meaningful_when_quote_is_already_empty() -> None:
    """`redact_top_quote` is a no-op when there is no quote to redact —
    the per-result `is_meaningful` must reflect the no-op, not the operator
    intent.
    """
    baseline_no_quote = {
        "calls": [
            {
                "id": "call-1",
                "direction": "overweight",
                "conviction": 0.7,
                "evidence_ids": ["ev-1"],
            }
        ],
        "top_quote": "",
    }
    results = generate_perturbations(baseline_no_quote)
    redact = next(r for r in results if r.kind is PerturbationKind.redact_top_quote)
    assert redact.is_meaningful is False


@pytest.mark.usefixtures("initialized_schema")
async def test_persist_counterfactual_gate_writes_rows_and_aggregate() -> None:
    from datetime import date

    async with session_factory() as session:
        run = ResearchRun(
            trade_date=date(2026, 5, 19),
            status=RunStatus.running,
            config={},
        )
        session.add(run)
        await session.commit()
        run_id = run.id

        baseline = _base_decision()
        results = generate_perturbations(baseline)
        outcome = evaluate_gate(results)
        gate_id = await persist_counterfactual_gate(
            session=session,
            run_id=run_id,
            brief_kind=BriefKind.macro,
            brief_id=None,
            results=results,
            outcome=outcome,
        )
        await session.commit()

    async with session_factory() as session:
        gate = (
            await session.execute(
                CounterfactualGateRun.__table__.select().where(
                    CounterfactualGateRun.id == gate_id
                )
            )
        ).one()
        assert gate.run_id == run_id
        assert gate.brief_kind == BriefKind.macro.value
        assert gate.perturbation_count == len(results)
        assert gate.meaningful_count == outcome.meaningful_count

        rows = (
            (
                await session.execute(
                    CounterfactualPerturbation.__table__.select().where(
                        CounterfactualPerturbation.run_id == run_id
                    )
                )
            )
            .mappings()
            .all()
        )
        assert len(rows) == len(results)
        kinds = {row["perturbation_kind"] for row in rows}
        assert kinds == {op.kind.value for op in operators()}
