"""Project brief schemas down to the agnostic `DecisionLike` shape.

Each brief kind contains a different list of decision-bearing items (macro
sector calls; sector company ideas; company → single thesis; portfolio
sector + company entries). The counterfactual harness operates on a
`DecisionLike` projection so that perturbation operators and gate logic are
brief-kind-agnostic.
"""

from __future__ import annotations

from app.schemas.company_thesis import CompanyThesis
from app.schemas.macro_brief import MacroBrief
from app.schemas.portfolio_brief import PortfolioBrief
from app.schemas.sector_brief import SectorBrief
from app.services.evals.counterfactual import DecisionLike


def project_macro_brief(brief: MacroBrief) -> DecisionLike:
    """Project a `MacroBrief` to a `DecisionLike` (one call per sector call)."""
    calls: list[dict[str, object]] = []
    for call in brief.sector_calls:
        calls.append(
            {
                "id": str(call.sector_entity_id),
                "direction": call.direction.value,
                "conviction": float(call.conviction),
                "evidence_ids": [str(eid) for eid in call.evidence_ids],
            }
        )
    top_quote = brief.cited_claims[0].exact_quote if brief.cited_claims else ""
    return {"calls": calls, "top_quote": top_quote}


def project_sector_brief(brief: SectorBrief) -> DecisionLike:
    """Project a `SectorBrief` to a `DecisionLike` (one call per company idea)."""
    calls: list[dict[str, object]] = []
    for idea in brief.companies:
        identifier = (
            str(idea.company_entity_id)
            if idea.company_entity_id is not None
            else idea.name
        )
        calls.append(
            {
                "id": identifier,
                "direction": idea.direction.value,
                "conviction": float(idea.conviction),
                "evidence_ids": [str(eid) for eid in idea.evidence_ids],
            }
        )
    top_quote = brief.cited_claims[0].exact_quote if brief.cited_claims else ""
    return {"calls": calls, "top_quote": top_quote}


def project_company_thesis(thesis: CompanyThesis) -> DecisionLike:
    """Project a `CompanyThesis` to a single-call `DecisionLike`."""
    calls: list[dict[str, object]] = [
        {
            "id": str(thesis.company_entity_id),
            "direction": thesis.direction.value,
            "conviction": float(thesis.conviction),
            "evidence_ids": [str(eid) for eid in thesis.evidence_ids],
        }
    ]
    top_quote = thesis.cited_claims[0].exact_quote if thesis.cited_claims else ""
    return {"calls": calls, "top_quote": top_quote}


def project_portfolio_brief(brief: PortfolioBrief) -> DecisionLike:
    """Project a `PortfolioBrief` to a `DecisionLike` over sectors + companies."""
    calls: list[dict[str, object]] = []
    for sector in brief.sectors:
        calls.append(
            {
                "id": f"sector::{sector.sector_entity_id}",
                "direction": sector.direction.value,
                "conviction": float(sector.conviction),
                "evidence_ids": [],
            }
        )
    for company in brief.companies:
        calls.append(
            {
                "id": f"company::{company.company_entity_id}",
                "direction": company.direction.value,
                "conviction": float(company.conviction),
                "evidence_ids": [],
            }
        )
    top_quote = brief.cited_claims[0].exact_quote if brief.cited_claims else ""
    return {"calls": calls, "top_quote": top_quote}


__all__ = [
    "project_company_thesis",
    "project_macro_brief",
    "project_portfolio_brief",
    "project_sector_brief",
]
