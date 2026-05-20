"""Phase 3 — belief engine and graph grounding.

Submodules:
- recompute: the pure `weighted_avg_decay_v1` formula plus dataclasses for
  belief inputs and the per-input breakdown that explains a computed score.
- trigger: session-bound helpers that mirror hypotheses as entities, query
  supporting / contradicting relations, run the formula and persist the
  result onto `Hypothesis.belief`, `Hypothesis.belief_history` and the
  `belief_recomputations` audit table.
"""

from app.services.belief.recompute import (
    BELIEF_COMPUTATION_METHOD,
    DEFAULT_HALF_LIFE_DAYS,
    BeliefInput,
    BeliefInputContribution,
    BeliefRecomputeResult,
    weighted_avg_decay_v1,
)
from app.services.belief.trigger import (
    ensure_hypothesis_entity,
    recompute_belief_for_hypothesis,
    recompute_beliefs_for_relations,
)

__all__ = [
    "BELIEF_COMPUTATION_METHOD",
    "DEFAULT_HALF_LIFE_DAYS",
    "BeliefInput",
    "BeliefInputContribution",
    "BeliefRecomputeResult",
    "ensure_hypothesis_entity",
    "recompute_belief_for_hypothesis",
    "recompute_beliefs_for_relations",
    "weighted_avg_decay_v1",
]
