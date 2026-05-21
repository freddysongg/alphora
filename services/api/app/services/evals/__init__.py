"""Phase 2 — Profit-Mirage Eval Gates.

Submodules:
- counterfactual: perturbation operators, decision-delta comparator,
  rejection-gate evaluator and persistence helper.
- leakage: post-cutoff holdout decay computation and persistence helper.
- brief_projection: brief → `DecisionLike` adapters.
- gate_runner: orchestrator-facing helpers that persist the gate and emit
  a warn-level run event on failure.
"""

from app.services.evals.brief_projection import (
    project_company_thesis,
    project_macro_brief,
    project_portfolio_brief,
    project_sector_brief,
)
from app.services.evals.counterfactual import (
    DEFAULT_CHANGE_RATE_THRESHOLD,
    CounterfactualGateOutcome,
    CounterfactualResult,
    DecisionLike,
    PerturbationOperator,
    decision_delta,
    decisions_changed,
    evaluate_gate,
    generate_perturbations,
    persist_counterfactual_gate,
    run_counterfactual_gate,
)
from app.services.evals.gate_runner import (
    COUNTERFACTUAL_GATE_FAILED_EVENT,
    run_gate_for_company_thesis,
    run_gate_for_macro_brief,
    run_gate_for_portfolio_brief,
    run_gate_for_sector_brief,
)
from app.services.evals.leakage import (
    DEFAULT_DECAY_THRESHOLD,
    LeakageOutcome,
    compute_case_decay,
    evaluate_leakage,
    persist_holdout_case,
    persist_leakage_run,
)

__all__ = [
    "COUNTERFACTUAL_GATE_FAILED_EVENT",
    "DEFAULT_CHANGE_RATE_THRESHOLD",
    "DEFAULT_DECAY_THRESHOLD",
    "CounterfactualGateOutcome",
    "CounterfactualResult",
    "DecisionLike",
    "LeakageOutcome",
    "PerturbationOperator",
    "compute_case_decay",
    "decision_delta",
    "decisions_changed",
    "evaluate_gate",
    "evaluate_leakage",
    "generate_perturbations",
    "persist_counterfactual_gate",
    "persist_holdout_case",
    "persist_leakage_run",
    "project_company_thesis",
    "project_macro_brief",
    "project_portfolio_brief",
    "project_sector_brief",
    "run_counterfactual_gate",
    "run_gate_for_company_thesis",
    "run_gate_for_macro_brief",
    "run_gate_for_portfolio_brief",
    "run_gate_for_sector_brief",
]
