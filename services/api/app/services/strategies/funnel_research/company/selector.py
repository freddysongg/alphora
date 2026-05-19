"""Company idea selection for Stage 3 fan-out.

Selects bounded, non-neutral company ideas from verified sector briefs using a
deterministic ordering. The selector does not resolve entities; later company
fan-out slices will map each idea to a canonical company entity before
persistence.
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass

from app.schemas.macro_brief import SectorCallDirection
from app.schemas.sector_brief import SectorBriefPublic, SectorCompanyIdea

MAX_COMPANY_DEEP_DIVES = 5
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class CompanyIdea:
    company_name: str
    ticker: str | None
    direction: SectorCallDirection
    conviction: float
    sector_entity_id: uuid.UUID
    sector_name: str
    evidence_ids: tuple[uuid.UUID, ...]
    sector_company_index: int


def select_companies(
    sector_briefs: list[SectorBriefPublic],
    *,
    max_count: int = MAX_COMPANY_DEEP_DIVES,
) -> list[CompanyIdea]:
    if max_count <= 0:
        return []

    ranked = sorted(_iter_candidates(sector_briefs), key=_sort_key)
    selected: list[CompanyIdea] = []
    seen_keys: set[str] = set()
    for idea in ranked:
        dedupe_key = _dedupe_key(idea)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        selected.append(idea)
        if len(selected) == max_count:
            break
    return selected


def _iter_candidates(sector_briefs: list[SectorBriefPublic]) -> list[CompanyIdea]:
    ideas: list[CompanyIdea] = []
    for public in sector_briefs:
        brief = public.brief
        for index, company in enumerate(brief.companies):
            if company.direction is SectorCallDirection.neutral:
                continue
            ideas.append(
                _to_company_idea(
                    company=company,
                    sector_entity_id=brief.sector_entity_id,
                    sector_name=brief.sector_name,
                    sector_company_index=index,
                )
            )
    return ideas


def _to_company_idea(
    *,
    company: SectorCompanyIdea,
    sector_entity_id: uuid.UUID,
    sector_name: str,
    sector_company_index: int,
) -> CompanyIdea:
    ticker = company.ticker.strip().upper() if company.ticker else None
    return CompanyIdea(
        company_name=company.name,
        ticker=ticker,
        direction=company.direction,
        conviction=company.conviction,
        sector_entity_id=sector_entity_id,
        sector_name=sector_name,
        evidence_ids=tuple(company.evidence_ids),
        sector_company_index=sector_company_index,
    )


def _sort_key(idea: CompanyIdea) -> tuple[int, float, str, int]:
    direction_rank = 0 if idea.direction is not SectorCallDirection.neutral else 1
    return (
        direction_rank,
        -idea.conviction,
        idea.sector_name,
        idea.sector_company_index,
    )


def _dedupe_key(idea: CompanyIdea) -> str:
    if idea.ticker:
        return f"ticker:{idea.ticker}"
    return f"name:{_normalize_company_name(idea.company_name)}"


def _normalize_company_name(name: str) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    return _WHITESPACE_RE.sub(" ", ascii_name.lower()).strip()


__all__ = [
    "MAX_COMPANY_DEEP_DIVES",
    "CompanyIdea",
    "select_companies",
]
