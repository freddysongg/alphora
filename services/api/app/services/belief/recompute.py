"""Pure belief recomputation formula: `weighted_avg_decay_v1`.

A *belief input* is a single relation that supports or contradicts a
hypothesis. Each input carries the sign (+1 for supports, -1 for
contradicts), the source's reliability score, the extractor's confidence,
the relation's relevance, and the timestamp at which the relation was
captured. The formula collapses these into a scalar belief in [0, 1] and
emits a per-input breakdown so the result is auditable.

The pipeline that gathers inputs and persists the result lives in
`app.services.belief.trigger`; this module is intentionally pure and
contains no I/O so the formula can be unit-tested against deterministic
fixtures.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

BELIEF_COMPUTATION_METHOD: Final[str] = "weighted_avg_decay_v1"
"""Identifier persisted on `belief_recomputations.computation_method`."""

DEFAULT_HALF_LIFE_DAYS: Final[float] = 90.0
"""Half-life for exponential time decay (90 days)."""

_NEUTRAL_BELIEF: Final[float] = 0.5


@dataclass(frozen=True)
class BeliefInput:
    """One relation that supports or contradicts a hypothesis."""

    relation_id: uuid.UUID
    relation_type: str
    from_id: uuid.UUID
    to_id: uuid.UUID
    source_id: uuid.UUID | None
    chunk_id: uuid.UUID | None
    quote: str | None
    is_explicit: bool
    sign: float
    reliability: float
    confidence: float
    relevance: float
    created_at: datetime


@dataclass(frozen=True)
class BeliefInputContribution:
    """Per-input breakdown so the computed belief is auditable."""

    relation_id: uuid.UUID
    relation_type: str
    from_id: uuid.UUID
    to_id: uuid.UUID
    source_id: uuid.UUID | None
    chunk_id: uuid.UUID | None
    quote: str | None
    is_explicit: bool
    sign: float
    reliability: float
    confidence: float
    relevance: float
    age_days: float
    decay: float
    weight: float
    signed_contribution: float

    def to_jsonable(self) -> dict[str, object]:
        return {
            "relation_id": str(self.relation_id),
            "relation_type": self.relation_type,
            "from_id": str(self.from_id),
            "to_id": str(self.to_id),
            "source_id": None if self.source_id is None else str(self.source_id),
            "chunk_id": None if self.chunk_id is None else str(self.chunk_id),
            "quote": self.quote,
            "is_explicit": self.is_explicit,
            "sign": self.sign,
            "reliability": self.reliability,
            "confidence": self.confidence,
            "relevance": self.relevance,
            "age_days": self.age_days,
            "decay": self.decay,
            "weight": self.weight,
            "signed_contribution": self.signed_contribution,
        }


@dataclass(frozen=True)
class BeliefRecomputeResult:
    belief: float
    contributions: list[BeliefInputContribution]
    total_weight: float
    weighted_signed_sum: float
    half_life_days: float
    computed_at: datetime


def weighted_avg_decay_v1(
    inputs: Sequence[BeliefInput],
    *,
    now: datetime,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> BeliefRecomputeResult:
    """Compute belief in [0, 1] from supporting / contradicting relations.

    For each input the contribution is::

        age_days = (now - created_at) / 1 day
        decay    = exp(-age_days / half_life_days)
        weight   = reliability * confidence * relevance * decay
        signed   = sign * weight

    The aggregate score is the weighted average of signs::

        score  = sum(signed) / sum(weight)        in [-1, +1]
        belief = (score + 1) / 2                   in [0, 1]

    When there are no inputs (or every weight is zero) belief is the
    neutral prior 0.5 and the breakdown is empty.
    """
    if half_life_days <= 0.0:
        raise ValueError("half_life_days must be positive")

    contributions: list[BeliefInputContribution] = []
    total_weight = 0.0
    weighted_signed_sum = 0.0

    for item in inputs:
        age_seconds = (now - item.created_at).total_seconds()
        age_days = age_seconds / 86_400.0 if age_seconds > 0 else 0.0
        decay = math.exp(-age_days / half_life_days)
        weight = item.reliability * item.confidence * item.relevance * decay
        signed = item.sign * weight

        contributions.append(
            BeliefInputContribution(
                relation_id=item.relation_id,
                relation_type=item.relation_type,
                from_id=item.from_id,
                to_id=item.to_id,
                source_id=item.source_id,
                chunk_id=item.chunk_id,
                quote=item.quote,
                is_explicit=item.is_explicit,
                sign=item.sign,
                reliability=item.reliability,
                confidence=item.confidence,
                relevance=item.relevance,
                age_days=age_days,
                decay=decay,
                weight=weight,
                signed_contribution=signed,
            )
        )

        total_weight += weight
        weighted_signed_sum += signed

    if total_weight <= 0.0:
        belief = _NEUTRAL_BELIEF
    else:
        score = weighted_signed_sum / total_weight
        score = max(-1.0, min(1.0, score))
        belief = (score + 1.0) / 2.0

    return BeliefRecomputeResult(
        belief=belief,
        contributions=contributions,
        total_weight=total_weight,
        weighted_signed_sum=weighted_signed_sum,
        half_life_days=half_life_days,
        computed_at=now,
    )


__all__ = [
    "BELIEF_COMPUTATION_METHOD",
    "DEFAULT_HALF_LIFE_DAYS",
    "BeliefInput",
    "BeliefInputContribution",
    "BeliefRecomputeResult",
    "weighted_avg_decay_v1",
]
