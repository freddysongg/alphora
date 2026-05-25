"""Read-only research-substrate context for the LLM judge (spec §6.5).

Pulls a bounded snapshot of Alphora's existing research data for a single
ticker — Entity row, recent active Hypothesis rows scoped to that entity,
the most recent CompanyThesis, the most recent SectorBrief for the
company's sector, the most recent MacroBrief, and a bounded set of
recent Evidence rows linked to those hypotheses. NO source-client fetches,
NO writes, NO LLM calls. The judge calls this synchronously inside its
evaluate() function before deciding whether to call the LLM at all.

`is_sparse(ctx)` returns True when the substrate has effectively nothing
to say about this specific ticker — no Entity, OR (no active Hypothesis
AND no CompanyThesis AND no SectorBrief tied to a recognized sector).
The judge takes the conservative-default branch on sparse context.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_company import CompanyThesis
from app.db.models_graph import (
    Entity,
    Evidence,
    Hypothesis,
    HypothesisStatus,
)
from app.db.models_macro import MacroBrief
from app.db.models_sector import SectorBrief

MAX_HYPOTHESES: Final[int] = 10
MAX_EVIDENCE: Final[int] = 10
MAX_CLAIM_TEXT_CHARS: Final[int] = 280
MAX_STRUCTURED_JSON_CHARS: Final[int] = 1024
HYPOTHESIS_ACTIVITY_WINDOW_DAYS: Final[int] = 90


@dataclass(frozen=True)
class JudgeContext:
    """Bounded research-substrate snapshot for a single ticker."""

    ticker: str
    entity_id: uuid.UUID | None
    entity_canonical_name: str | None
    hypotheses: list[dict[str, object]] = field(default_factory=list)
    company_thesis: dict[str, object] | None = None
    sector_brief: dict[str, object] | None = None
    macro_brief: dict[str, object] | None = None
    evidence: list[dict[str, object]] = field(default_factory=list)


async def gather_context(
    session: AsyncSession,
    *,
    ticker: str,
) -> JudgeContext:
    """Read the research substrate for `ticker`. See module docstring."""
    ticker_norm = ticker.upper()
    entity = await _find_entity(session, ticker_norm)
    if entity is None:
        macro_brief = await _latest_macro_brief(session)
        return JudgeContext(
            ticker=ticker_norm,
            entity_id=None,
            entity_canonical_name=None,
            macro_brief=macro_brief,
        )

    hypotheses = await _gather_hypotheses(session, entity_id=entity.id)
    company_thesis = await _latest_company_thesis(session, entity_id=entity.id)
    sector_brief = await _latest_sector_brief_for_company(
        session, company_thesis=company_thesis
    )
    macro_brief = await _latest_macro_brief(session)
    evidence = await _gather_evidence(
        session,
        hypotheses_ids=[uuid.UUID(str(h["id"])) for h in hypotheses],
    )

    return JudgeContext(
        ticker=ticker_norm,
        entity_id=entity.id,
        entity_canonical_name=entity.canonical_name,
        hypotheses=hypotheses,
        company_thesis=company_thesis,
        sector_brief=sector_brief,
        macro_brief=macro_brief,
        evidence=evidence,
    )


def is_sparse(ctx: JudgeContext) -> bool:
    """Conservative-default predicate.

    Sparse = no Entity OR (no active Hypothesis AND no recent
    CompanyThesis AND no SectorBrief). MacroBrief alone is NOT enough
    because the judge is making a ticker-specific call.
    """
    if ctx.entity_id is None:
        return True
    if not ctx.hypotheses and ctx.company_thesis is None and ctx.sector_brief is None:
        return True
    return False


async def _find_entity(
    session: AsyncSession,
    ticker_norm: str,
) -> Entity | None:
    """Find the highest-confidence company Entity by exact ticker match."""
    stmt = (
        select(Entity)
        .where(Entity.ticker_normalized == ticker_norm)
        .where(Entity.type == "company")
        .order_by(Entity.confidence.desc(), Entity.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _gather_hypotheses(
    session: AsyncSession,
    *,
    entity_id: uuid.UUID,
) -> list[dict[str, object]]:
    """Active hypotheses touching this entity, ranked by belief then recency.

    Null-belief rows are excluded so the ORDER BY belief DESC is stable
    across SQLite (which does not guarantee NULLS LAST behaviour in all
    versions) and Postgres alike. Rows with no belief assigned have not
    been evaluated and are less useful for a judge context than even a
    low-confidence scored hypothesis.
    """
    cutoff = datetime.now(UTC) - timedelta(days=HYPOTHESIS_ACTIVITY_WINDOW_DAYS)
    stmt = (
        select(Hypothesis)
        .where(Hypothesis.status == HypothesisStatus.active.value)
        .where(Hypothesis.last_activity_at >= cutoff)
        .where(Hypothesis.belief.is_not(None))
        .order_by(Hypothesis.belief.desc(), Hypothesis.last_activity_at.desc())
    )
    candidates = (await session.execute(stmt)).scalars().all()
    entity_id_str = str(entity_id)
    matches: list[Hypothesis] = []
    for h in candidates:
        scope = h.scope_entity_ids or []
        if entity_id_str in scope:
            matches.append(h)
        if len(matches) >= MAX_HYPOTHESES:
            break
    return [
        {
            "id": str(h.id),
            "claim_text": _truncate(h.claim_text, MAX_CLAIM_TEXT_CHARS),
            "belief": h.belief,
            "last_activity_at": (
                h.last_activity_at.isoformat()
                if h.last_activity_at is not None
                else None
            ),
        }
        for h in matches
    ]


async def _latest_company_thesis(
    session: AsyncSession,
    *,
    entity_id: uuid.UUID,
) -> dict[str, object] | None:
    stmt = (
        select(CompanyThesis)
        .where(CompanyThesis.company_entity_id == entity_id)
        .order_by(CompanyThesis.created_at.desc())
        .limit(1)
    )
    thesis = (await session.execute(stmt)).scalar_one_or_none()
    if thesis is None:
        return None
    payload = thesis.payload if isinstance(thesis.payload, dict) else {}
    return {
        "id": str(thesis.id),
        "direction": thesis.direction,
        "sector_entity_id": str(thesis.sector_entity_id),
        "created_at": thesis.created_at.isoformat(),
        "summary": payload.get("summary"),
    }


async def _latest_sector_brief_for_company(
    session: AsyncSession,
    *,
    company_thesis: dict[str, object] | None,
) -> dict[str, object] | None:
    if company_thesis is None:
        return None
    sector_id_raw = company_thesis.get("sector_entity_id")
    if not isinstance(sector_id_raw, str):
        return None
    sector_id = uuid.UUID(sector_id_raw)
    stmt = (
        select(SectorBrief)
        .where(SectorBrief.sector_entity_id == sector_id)
        .order_by(SectorBrief.created_at.desc())
        .limit(1)
    )
    brief = (await session.execute(stmt)).scalar_one_or_none()
    if brief is None:
        return None
    payload = brief.payload if isinstance(brief.payload, dict) else {}
    return {
        "id": str(brief.id),
        "direction": brief.direction,
        "sector_entity_id": str(brief.sector_entity_id),
        "created_at": brief.created_at.isoformat(),
        "summary": payload.get("summary"),
    }


async def _latest_macro_brief(
    session: AsyncSession,
) -> dict[str, object] | None:
    stmt = (
        select(MacroBrief)
        .order_by(MacroBrief.created_at.desc())
        .limit(1)
    )
    brief = (await session.execute(stmt)).scalar_one_or_none()
    if brief is None:
        return None
    return {
        "id": str(brief.id),
        "created_at": brief.created_at.isoformat(),
        "themes": brief.themes[:5],
        "sector_calls": brief.sector_calls[:5],
    }


async def _gather_evidence(
    session: AsyncSession,
    *,
    hypotheses_ids: list[uuid.UUID],
) -> list[dict[str, object]]:
    """Recent Evidence rows. Phase 6 v1 returns the latest MAX_EVIDENCE rows
    across all sources; Phase 9+ may scope to evidence linked to the
    selected hypotheses via the relations graph. For now the heuristic is
    'newest matters most.'
    """
    del hypotheses_ids
    stmt = (
        select(Evidence)
        .order_by(Evidence.extracted_at.desc())
        .limit(MAX_EVIDENCE)
    )
    evs = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(e.id),
            "source": e.source,
            "document_id": e.document_id,
            "extracted_at": e.extracted_at.isoformat(),
            "structured": _truncate_json_dump(e.structured, MAX_STRUCTURED_JSON_CHARS),
        }
        for e in evs
    ]


def _truncate(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _truncate_json_dump(
    value: dict[str, object] | None, limit: int
) -> str | None:
    if value is None:
        return None
    dumped = json.dumps(value, sort_keys=True, default=str)
    if len(dumped) <= limit:
        return dumped
    return dumped[: limit - 1] + "…"


__all__ = [
    "HYPOTHESIS_ACTIVITY_WINDOW_DAYS",
    "MAX_CLAIM_TEXT_CHARS",
    "MAX_EVIDENCE",
    "MAX_HYPOTHESES",
    "MAX_STRUCTURED_JSON_CHARS",
    "JudgeContext",
    "gather_context",
    "is_sparse",
]
