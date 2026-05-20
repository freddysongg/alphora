"""Orchestrator-facing helper: run the counterfactual gate against a brief
projection, persist the gate + perturbations, and emit a warn-level run
event when the gate fails. The caller commits the session.
"""

from __future__ import annotations

import uuid
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_evals import BriefKind
from app.db.models_runs import RunEventLevel
from app.schemas.company_thesis import CompanyThesis
from app.schemas.macro_brief import MacroBrief
from app.schemas.portfolio_brief import PortfolioBrief
from app.schemas.sector_brief import SectorBrief
from app.services.evals.brief_projection import (
    project_company_thesis,
    project_macro_brief,
    project_portfolio_brief,
    project_sector_brief,
)
from app.services.evals.counterfactual import (
    CounterfactualGateOutcome,
    DecisionLike,
    run_counterfactual_gate,
)
from app.services.run_events import emit_run_event

COUNTERFACTUAL_GATE_FAILED_EVENT: Final[str] = "counterfactual_gate_failed"


async def run_gate_for_macro_brief(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    brief_id: uuid.UUID | None,
    brief: MacroBrief,
) -> CounterfactualGateOutcome:
    return await _run_gate(
        session=session,
        run_id=run_id,
        brief_kind=BriefKind.macro,
        brief_id=brief_id,
        baseline=project_macro_brief(brief),
    )


async def run_gate_for_sector_brief(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    brief_id: uuid.UUID | None,
    brief: SectorBrief,
) -> CounterfactualGateOutcome:
    return await _run_gate(
        session=session,
        run_id=run_id,
        brief_kind=BriefKind.sector,
        brief_id=brief_id,
        baseline=project_sector_brief(brief),
    )


async def run_gate_for_company_thesis(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    brief_id: uuid.UUID | None,
    thesis: CompanyThesis,
) -> CounterfactualGateOutcome:
    return await _run_gate(
        session=session,
        run_id=run_id,
        brief_kind=BriefKind.company,
        brief_id=brief_id,
        baseline=project_company_thesis(thesis),
    )


async def run_gate_for_portfolio_brief(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    brief_id: uuid.UUID | None,
    brief: PortfolioBrief,
) -> CounterfactualGateOutcome:
    return await _run_gate(
        session=session,
        run_id=run_id,
        brief_kind=BriefKind.portfolio,
        brief_id=brief_id,
        baseline=project_portfolio_brief(brief),
    )


async def _run_gate(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    brief_kind: BriefKind,
    brief_id: uuid.UUID | None,
    baseline: DecisionLike,
) -> CounterfactualGateOutcome:
    outcome = await run_counterfactual_gate(
        session=session,
        run_id=run_id,
        brief_kind=brief_kind,
        brief_id=brief_id,
        baseline=baseline,
    )
    if not outcome.passed:
        emit_run_event(
            session,
            run_id=run_id,
            level=RunEventLevel.warn,
            message=_failure_message(brief_kind, outcome),
            data={
                "event": COUNTERFACTUAL_GATE_FAILED_EVENT,
                "brief_kind": brief_kind.value,
                "brief_id": str(brief_id) if brief_id is not None else None,
                "change_rate": outcome.change_rate,
                "threshold": outcome.threshold,
                "meaningful_count": outcome.meaningful_count,
                "meaningful_changed_count": outcome.meaningful_changed_count,
            },
        )
    return outcome


def _failure_message(
    brief_kind: BriefKind, outcome: CounterfactualGateOutcome
) -> str:
    rate_percent = outcome.change_rate * 100.0
    threshold_percent = outcome.threshold * 100.0
    return (
        f"counterfactual gate failed for {brief_kind.value} brief: "
        f"{outcome.meaningful_changed_count}/{outcome.meaningful_count} "
        f"meaningful perturbations changed the decision "
        f"({rate_percent:.0f}% < {threshold_percent:.0f}% threshold)"
    )


__all__ = [
    "COUNTERFACTUAL_GATE_FAILED_EVENT",
    "run_gate_for_company_thesis",
    "run_gate_for_macro_brief",
    "run_gate_for_portfolio_brief",
    "run_gate_for_sector_brief",
]
