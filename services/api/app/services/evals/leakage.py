"""Leakage detection harness.

Each *holdout case* persists a `full_decision` (the decision when the
synthesizer is run with all evidence, including post-cutoff) alongside a
`restricted_decision` (the decision when the synthesizer is restricted to
pre-cutoff evidence only). The harness then computes:

- `agreement`: a normalized 0..1 similarity between the two decisions.
- `decay = 1 - agreement`: how much the decision degrades when post-cutoff
  evidence is withheld. Larger decay means the decision was overly reliant
  on data that was unavailable at the cutoff — i.e. it is leaking.

A `leakage_run` aggregates a set of cases and flags the aggregate when
mean decay exceeds the configured threshold (default 30%).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_evals import LeakageHoldoutCase, LeakageRun
from app.services.evals.counterfactual import (
    DecisionLike,
    decision_delta,
    decisions_changed,
)

DEFAULT_DECAY_THRESHOLD: Final[float] = 0.3
"""Flag the leakage run when mean decay exceeds this threshold."""


@dataclass(frozen=True)
class CaseDecay:
    agreement: float
    decay: float
    delta: dict[str, object]


@dataclass(frozen=True)
class LeakageOutcome:
    case_count: int
    mean_decay: float
    max_decay: float
    threshold: float
    flagged: bool


def compute_case_decay(
    *,
    full_decision: DecisionLike,
    restricted_decision: DecisionLike,
) -> CaseDecay:
    """Compute agreement + decay between full and restricted decisions.

    Agreement combines three signals:
    - Direction agreement on shared call ids (weight 0.6).
    - Mean conviction proximity on shared call ids (weight 0.3).
    - Set agreement (Jaccard) over call ids (weight 0.1).

    When there are no shared call ids the direction/conviction weights
    collapse onto the set agreement (which falls to 0 if both call lists
    are disjoint), so decay is bounded by the set difference.

    Edge case: when *both* decisions have no calls at all (mutual abstention),
    agreement is 1.0 — the two runs reached the same null decision, so decay
    must be 0.0. Without this branch the direction/conviction weights collapse
    to 0 even though set agreement is vacuously 1, producing 0.9 decay on a
    pair of identical no-call decisions and flagging the holdout incorrectly.
    """
    delta = decision_delta(full_decision, restricted_decision)
    full_calls = _calls_by_id(full_decision)
    restricted_calls = _calls_by_id(restricted_decision)
    shared_ids = set(full_calls).intersection(restricted_calls)
    union = set(full_calls).union(restricted_calls)

    if not union:
        return CaseDecay(agreement=1.0, decay=0.0, delta=delta)

    if shared_ids:
        direction_matches = sum(
            1
            for cid in shared_ids
            if _direction(full_calls[cid]) == _direction(restricted_calls[cid])
        )
        direction_agreement = direction_matches / len(shared_ids)

        conviction_deltas = [
            abs(_conviction(full_calls[cid]) - _conviction(restricted_calls[cid]))
            for cid in shared_ids
        ]
        conviction_agreement = 1.0 - sum(conviction_deltas) / len(shared_ids)
        conviction_agreement = max(0.0, min(1.0, conviction_agreement))
    else:
        direction_agreement = 0.0
        conviction_agreement = 0.0

    set_agreement = len(shared_ids) / len(union)

    agreement = (
        0.6 * direction_agreement
        + 0.3 * conviction_agreement
        + 0.1 * set_agreement
    )
    agreement = max(0.0, min(1.0, agreement))
    return CaseDecay(agreement=agreement, decay=1.0 - agreement, delta=delta)


def evaluate_leakage(
    decays: Sequence[float],
    *,
    threshold: float = DEFAULT_DECAY_THRESHOLD,
) -> LeakageOutcome:
    """Aggregate decay values into a leakage outcome."""
    if not decays:
        return LeakageOutcome(
            case_count=0,
            mean_decay=0.0,
            max_decay=0.0,
            threshold=threshold,
            flagged=False,
        )
    mean_decay = sum(decays) / len(decays)
    max_decay = max(decays)
    return LeakageOutcome(
        case_count=len(decays),
        mean_decay=mean_decay,
        max_decay=max_decay,
        threshold=threshold,
        flagged=mean_decay > threshold,
    )


async def persist_holdout_case(
    *,
    session: AsyncSession,
    case_name: str,
    cutoff_at: object,
    full_decision: DecisionLike,
    restricted_decision: DecisionLike,
) -> LeakageHoldoutCase:
    """Compute decay, persist case row, return the persisted row."""
    if not hasattr(cutoff_at, "isoformat"):
        raise ValueError("cutoff_at must be a datetime-like value")
    case_decay = compute_case_decay(
        full_decision=full_decision,
        restricted_decision=restricted_decision,
    )
    row = LeakageHoldoutCase(
        case_name=case_name,
        cutoff_at=cutoff_at,
        full_decision=full_decision,
        restricted_decision=restricted_decision,
        agreement=case_decay.agreement,
        decay=case_decay.decay,
    )
    session.add(row)
    await session.flush()
    return row


async def persist_leakage_run(
    *,
    session: AsyncSession,
    run_id: uuid.UUID | None,
    cases: Sequence[LeakageHoldoutCase],
    threshold: float = DEFAULT_DECAY_THRESHOLD,
) -> tuple[LeakageRun, LeakageOutcome]:
    """Aggregate over the provided cases, persist a leakage_runs row."""
    outcome = evaluate_leakage(
        [case.decay for case in cases], threshold=threshold
    )
    row = LeakageRun(
        run_id=run_id,
        case_count=outcome.case_count,
        mean_decay=outcome.mean_decay,
        max_decay=outcome.max_decay,
        threshold=outcome.threshold,
        flagged=outcome.flagged,
        case_ids=[str(case.id) for case in cases],
    )
    session.add(row)
    await session.flush()
    return row, outcome


def _calls_by_id(decision: DecisionLike) -> dict[str, dict[str, object]]:
    calls = decision.get("calls")
    if not isinstance(calls, list):
        return {}
    by_id: dict[str, dict[str, object]] = {}
    for call in calls:
        if not isinstance(call, dict):
            continue
        identifier = call.get("id")
        if not isinstance(identifier, str) or not identifier:
            continue
        by_id[identifier] = call
    return by_id


def _direction(call: dict[str, object]) -> str | None:
    direction = call.get("direction")
    return direction if isinstance(direction, str) else None


def _conviction(call: dict[str, object]) -> float:
    conviction = call.get("conviction")
    if isinstance(conviction, bool):
        return 0.0
    if isinstance(conviction, (int, float)):
        return float(conviction)
    return 0.0


__all__ = [
    "DEFAULT_DECAY_THRESHOLD",
    "CaseDecay",
    "LeakageOutcome",
    "compute_case_decay",
    "decision_delta",
    "decisions_changed",
    "evaluate_leakage",
    "persist_holdout_case",
    "persist_leakage_run",
]
