"""Counterfactual perturbation harness for Profit-Mirage eval gates.

A *decision* is the brief-kind-agnostic projection a brief exposes for the
purpose of evaluation:

```
{
    "calls": [
        {"id": "...", "direction": "overweight|underweight|neutral",
         "conviction": 0.7, "evidence_ids": ["..."]},
        ...
    ],
    "top_quote": "...",
}
```

`generate_perturbations` applies a fixed catalogue of operators to a baseline
decision, producing perturbed decisions. The catalogue is deterministic so
that the same baseline always yields the same perturbations — this is
required by the deterministic-fixture-test verification.

`evaluate_gate` then computes a change-rate over *meaningful* perturbations
(operators tagged as `is_meaningful=True`). The default threshold is 0.5:
when meaningful perturbations change the decision in less than 50% of cases,
the gate fails — that is the Profit-Mirage signal.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_evals import (
    BriefKind,
    CounterfactualGateRun,
    CounterfactualPerturbation,
    PerturbationKind,
)

DecisionLike = dict[str, object]
"""A brief-kind-agnostic decision projection. See module docstring."""

DEFAULT_CHANGE_RATE_THRESHOLD: Final[float] = 0.5
"""Failure threshold: when meaningful-change-rate < this, the gate fails."""

_DIRECTION_FLIP: Final[dict[str, str]] = {
    "overweight": "underweight",
    "underweight": "overweight",
    "neutral": "overweight",
}

_CONVICTION_FLOOR_DELTA: Final[float] = 0.4
"""How far the `lower_top_call_conviction` operator drops conviction."""


@dataclass(frozen=True)
class PerturbationOperator:
    """One deterministic perturbation operator.

    `is_meaningful` tags the operator as one whose effect on the decision
    *should* matter to a calibrated synthesizer. The gate is evaluated only
    over meaningful operators; marginal ones (e.g. swap ordering) are
    persisted so reviewers can see them but do not count toward the rate.
    """

    kind: PerturbationKind
    is_meaningful: bool
    apply: Callable[[DecisionLike], tuple[DecisionLike, dict[str, object]]]


@dataclass(frozen=True)
class CounterfactualResult:
    """One perturbation result for a single brief."""

    kind: PerturbationKind
    is_meaningful: bool
    perturbation_input: dict[str, object]
    baseline_output: DecisionLike
    perturbed_output: DecisionLike
    decision_delta: dict[str, object]
    decision_changed: bool


@dataclass(frozen=True)
class CounterfactualGateOutcome:
    """Aggregate gate evaluation over a set of perturbation results."""

    perturbation_count: int
    meaningful_count: int
    meaningful_changed_count: int
    change_rate: float
    threshold: float
    passed: bool


def _clone_decision(decision: DecisionLike) -> DecisionLike:
    """Deep-copy a decision via JSON round-trip for safe mutation.

    Decisions hold only JSON-safe primitives + nested lists/dicts so a
    shallow per-list copy plus per-call dict copy is sufficient and avoids
    the cost of a full json round-trip.
    """
    calls_raw = decision.get("calls")
    calls = list(calls_raw) if isinstance(calls_raw, list) else []
    cloned_calls: list[dict[str, object]] = []
    for call in calls:
        if isinstance(call, dict):
            cloned_calls.append(dict(call))
    cloned: DecisionLike = dict(decision)
    cloned["calls"] = cloned_calls
    return cloned


def _drop_top_evidence(
    decision: DecisionLike,
) -> tuple[DecisionLike, dict[str, object]]:
    cloned = _clone_decision(decision)
    calls = cloned.get("calls")
    if not isinstance(calls, list) or not calls:
        return cloned, {"removed_evidence_id": None}
    first = calls[0]
    if not isinstance(first, dict):
        return cloned, {"removed_evidence_id": None}
    evidence = first.get("evidence_ids")
    removed: object | None = None
    if isinstance(evidence, list) and evidence:
        first = dict(first)
        evidence_copy = list(evidence)
        removed = evidence_copy.pop(0)
        first["evidence_ids"] = evidence_copy
        if not evidence_copy:
            first["conviction"] = 0.0
            first["direction"] = "neutral"
        calls[0] = first
    return cloned, {"removed_evidence_id": removed}


def _flip_top_call_direction(
    decision: DecisionLike,
) -> tuple[DecisionLike, dict[str, object]]:
    cloned = _clone_decision(decision)
    calls = cloned.get("calls")
    if not isinstance(calls, list) or not calls:
        return cloned, {"flipped_call_id": None}
    first = calls[0]
    if not isinstance(first, dict):
        return cloned, {"flipped_call_id": None}
    direction = first.get("direction")
    if not isinstance(direction, str):
        return cloned, {"flipped_call_id": first.get("id")}
    new_direction = _DIRECTION_FLIP.get(direction, "neutral")
    first = dict(first)
    first["direction"] = new_direction
    calls[0] = first
    return cloned, {
        "flipped_call_id": first.get("id"),
        "from_direction": direction,
        "to_direction": new_direction,
    }


def _redact_top_quote(
    decision: DecisionLike,
) -> tuple[DecisionLike, dict[str, object]]:
    cloned = _clone_decision(decision)
    previous = cloned.get("top_quote")
    cloned["top_quote"] = ""
    return cloned, {"redacted_quote": previous if isinstance(previous, str) else None}


def _lower_top_call_conviction(
    decision: DecisionLike,
) -> tuple[DecisionLike, dict[str, object]]:
    cloned = _clone_decision(decision)
    calls = cloned.get("calls")
    if not isinstance(calls, list) or not calls:
        return cloned, {"lowered_call_id": None}
    first = calls[0]
    if not isinstance(first, dict):
        return cloned, {"lowered_call_id": None}
    conviction = first.get("conviction")
    if not isinstance(conviction, (int, float)):
        return cloned, {"lowered_call_id": first.get("id")}
    new_conviction = max(0.0, float(conviction) - _CONVICTION_FLOOR_DELTA)
    first = dict(first)
    first["conviction"] = new_conviction
    if new_conviction < 0.2:
        first["direction"] = "neutral"
    calls[0] = first
    return cloned, {
        "lowered_call_id": first.get("id"),
        "from_conviction": conviction,
        "to_conviction": new_conviction,
    }


def _swap_call_ordering(
    decision: DecisionLike,
) -> tuple[DecisionLike, dict[str, object]]:
    cloned = _clone_decision(decision)
    calls = cloned.get("calls")
    if not isinstance(calls, list) or len(calls) < 2:
        return cloned, {"swapped": False}
    reversed_calls = list(reversed(calls))
    cloned["calls"] = reversed_calls
    return cloned, {"swapped": True, "call_count": len(calls)}


_OPERATORS: Final[tuple[PerturbationOperator, ...]] = (
    PerturbationOperator(
        kind=PerturbationKind.drop_top_evidence,
        is_meaningful=True,
        apply=_drop_top_evidence,
    ),
    PerturbationOperator(
        kind=PerturbationKind.flip_top_call_direction,
        is_meaningful=True,
        apply=_flip_top_call_direction,
    ),
    PerturbationOperator(
        kind=PerturbationKind.redact_top_quote,
        is_meaningful=True,
        apply=_redact_top_quote,
    ),
    PerturbationOperator(
        kind=PerturbationKind.lower_top_call_conviction,
        is_meaningful=True,
        apply=_lower_top_call_conviction,
    ),
    PerturbationOperator(
        kind=PerturbationKind.swap_call_ordering,
        is_meaningful=False,
        apply=_swap_call_ordering,
    ),
)


def operators() -> tuple[PerturbationOperator, ...]:
    """Return the catalogue of perturbation operators in deterministic order."""
    return _OPERATORS


def decision_delta(
    baseline: DecisionLike, perturbed: DecisionLike
) -> dict[str, object]:
    """Compute a structured comparator between two decision projections."""
    baseline_calls = _calls_list(baseline)
    perturbed_calls = _calls_list(perturbed)
    by_id_baseline: dict[str, dict[str, object]] = {}
    by_id_perturbed: dict[str, dict[str, object]] = {}
    for call in baseline_calls:
        identifier = _call_id(call)
        if identifier is not None:
            by_id_baseline[identifier] = call
    for call in perturbed_calls:
        identifier = _call_id(call)
        if identifier is not None:
            by_id_perturbed[identifier] = call

    direction_changes: list[dict[str, object]] = []
    conviction_changes: list[dict[str, object]] = []
    added: list[str] = []
    removed: list[str] = []

    for identifier, perturbed_call in by_id_perturbed.items():
        baseline_call = by_id_baseline.get(identifier)
        if baseline_call is None:
            added.append(identifier)
            continue
        baseline_direction = _read_str(baseline_call.get("direction"))
        perturbed_direction = _read_str(perturbed_call.get("direction"))
        if baseline_direction != perturbed_direction:
            direction_changes.append(
                {
                    "id": identifier,
                    "from": baseline_direction,
                    "to": perturbed_direction,
                }
            )
        baseline_conviction = _read_float(baseline_call.get("conviction"))
        perturbed_conviction = _read_float(perturbed_call.get("conviction"))
        if baseline_conviction is None or perturbed_conviction is None:
            continue
        if abs(baseline_conviction - perturbed_conviction) > 1e-9:
            conviction_changes.append(
                {
                    "id": identifier,
                    "from": baseline_conviction,
                    "to": perturbed_conviction,
                    "delta": perturbed_conviction - baseline_conviction,
                }
            )
    for identifier in by_id_baseline:
        if identifier not in by_id_perturbed:
            removed.append(identifier)

    baseline_order = [
        _call_id(call) for call in baseline_calls if _call_id(call) is not None
    ]
    perturbed_order = [
        _call_id(call) for call in perturbed_calls if _call_id(call) is not None
    ]
    order_changed = baseline_order != perturbed_order

    baseline_quote = _read_str(baseline.get("top_quote"))
    perturbed_quote = _read_str(perturbed.get("top_quote"))
    quote_changed = baseline_quote != perturbed_quote

    return {
        "direction_changes": direction_changes,
        "conviction_changes": conviction_changes,
        "added_call_ids": added,
        "removed_call_ids": removed,
        "order_changed": order_changed,
        "quote_changed": quote_changed,
    }


def decisions_changed(delta: dict[str, object]) -> bool:
    """Returns True when the delta represents a *decision change*.

    Definition: any direction flip OR any conviction shift >= 0.2 OR any
    added/removed call. Pure ordering swaps and quote text changes do NOT
    count as a decision change — those are tracked but considered cosmetic.
    """
    direction_changes = delta.get("direction_changes")
    if isinstance(direction_changes, list) and direction_changes:
        return True
    conviction_changes = delta.get("conviction_changes")
    if isinstance(conviction_changes, list):
        for entry in conviction_changes:
            if not isinstance(entry, dict):
                continue
            shift = entry.get("delta")
            if isinstance(shift, (int, float)) and abs(shift) >= 0.2:
                return True
    added = delta.get("added_call_ids")
    if isinstance(added, list) and added:
        return True
    removed = delta.get("removed_call_ids")
    if isinstance(removed, list) and removed:
        return True
    return False


def generate_perturbations(
    baseline: DecisionLike,
) -> list[CounterfactualResult]:
    """Apply each operator in the catalogue, returning results in order.

    A *meaningful* operator becomes a no-op when the baseline has nothing
    to perturb (e.g. flipping the top call on a brief that contains no
    calls). In that case the operator's intent does not translate into an
    actual mutation, so the per-result `is_meaningful` is demoted to False —
    otherwise the rejection gate counts no-op perturbations as failed-to-
    change-the-decision, which would fail vacuous briefs that should pass
    vacuously.
    """
    results: list[CounterfactualResult] = []
    for operator in _OPERATORS:
        perturbed, perturbation_input = operator.apply(baseline)
        delta = decision_delta(baseline, perturbed)
        is_no_op = perturbed == baseline
        results.append(
            CounterfactualResult(
                kind=operator.kind,
                is_meaningful=operator.is_meaningful and not is_no_op,
                perturbation_input=perturbation_input,
                baseline_output=baseline,
                perturbed_output=perturbed,
                decision_delta=delta,
                decision_changed=decisions_changed(delta),
            )
        )
    return results


def evaluate_gate(
    results: Sequence[CounterfactualResult],
    *,
    threshold: float = DEFAULT_CHANGE_RATE_THRESHOLD,
) -> CounterfactualGateOutcome:
    """Compute the gate outcome from a list of perturbation results.

    Definition of `passed`: the meaningful change-rate must be >= threshold.
    Edge case: when the baseline has no meaningful perturbations (e.g. empty
    decision), the gate passes vacuously and the change rate is 0.0 — the
    persistence + UI layer surface this so reviewers can spot vacuous
    passes.
    """
    meaningful = [r for r in results if r.is_meaningful]
    meaningful_changed = [r for r in meaningful if r.decision_changed]
    if not meaningful:
        return CounterfactualGateOutcome(
            perturbation_count=len(results),
            meaningful_count=0,
            meaningful_changed_count=0,
            change_rate=0.0,
            threshold=threshold,
            passed=True,
        )
    change_rate = len(meaningful_changed) / len(meaningful)
    passed = change_rate >= threshold
    return CounterfactualGateOutcome(
        perturbation_count=len(results),
        meaningful_count=len(meaningful),
        meaningful_changed_count=len(meaningful_changed),
        change_rate=change_rate,
        threshold=threshold,
        passed=passed,
    )


async def persist_counterfactual_gate(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    brief_kind: BriefKind,
    brief_id: uuid.UUID | None,
    results: Sequence[CounterfactualResult],
    outcome: CounterfactualGateOutcome,
) -> uuid.UUID:
    """Insert one gate row plus one perturbation row per result.

    Returns the gate row id. Callers are responsible for committing.
    """
    for result in results:
        session.add(
            CounterfactualPerturbation(
                run_id=run_id,
                brief_kind=brief_kind.value,
                brief_id=brief_id,
                perturbation_kind=result.kind.value,
                perturbation_input=result.perturbation_input,
                baseline_output=result.baseline_output,
                perturbed_output=result.perturbed_output,
                decision_delta=result.decision_delta,
                is_meaningful=result.is_meaningful,
                decision_changed=result.decision_changed,
            )
        )
    gate = CounterfactualGateRun(
        run_id=run_id,
        brief_kind=brief_kind.value,
        brief_id=brief_id,
        perturbation_count=outcome.perturbation_count,
        meaningful_count=outcome.meaningful_count,
        meaningful_changed_count=outcome.meaningful_changed_count,
        change_rate=outcome.change_rate,
        threshold=outcome.threshold,
        passed=outcome.passed,
    )
    session.add(gate)
    await session.flush()
    return gate.id


async def run_counterfactual_gate(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    brief_kind: BriefKind,
    brief_id: uuid.UUID | None,
    baseline: DecisionLike,
    threshold: float = DEFAULT_CHANGE_RATE_THRESHOLD,
) -> CounterfactualGateOutcome:
    """End-to-end helper: generate, evaluate, and persist a counterfactual gate."""
    results = generate_perturbations(baseline)
    outcome = evaluate_gate(results, threshold=threshold)
    await persist_counterfactual_gate(
        session=session,
        run_id=run_id,
        brief_kind=brief_kind,
        brief_id=brief_id,
        results=results,
        outcome=outcome,
    )
    return outcome


def _calls_list(decision: DecisionLike) -> list[dict[str, object]]:
    calls = decision.get("calls")
    if not isinstance(calls, list):
        return []
    return [c for c in calls if isinstance(c, dict)]


def _call_id(call: dict[str, object]) -> str | None:
    identifier = call.get("id")
    if isinstance(identifier, str) and identifier:
        return identifier
    return None


def _read_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _read_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


__all__ = [
    "DEFAULT_CHANGE_RATE_THRESHOLD",
    "CounterfactualGateOutcome",
    "CounterfactualResult",
    "DecisionLike",
    "PerturbationOperator",
    "decision_delta",
    "decisions_changed",
    "evaluate_gate",
    "generate_perturbations",
    "operators",
    "persist_counterfactual_gate",
    "run_counterfactual_gate",
]
