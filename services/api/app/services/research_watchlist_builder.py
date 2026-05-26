"""Research-driven watchlist builder (spec §4.2 / §6.6).

Queries Alphora's existing Hypothesis/Entity graph for active hypotheses
with recent activity and belief above a threshold; extracts the company
tickers they scope; replaces the target watchlist's members with that
set.

THIS IS A PARAMETERIZED DB QUERY, NOT AN LLM CALL. The "autonomous LLM
universe curator" was explicitly rejected -- see
.context/notes/feedback_rejected_alternatives.md.

Membership selection:
  1. Hypothesis.status == active
  2. Hypothesis.last_activity_at >= now - evidence_window_hours
  3. Hypothesis.belief >= min_belief
  4. Hypothesis.scope_entity_ids -> Entity where type=='company'
     AND ticker_normalized is not null
  5. Deduplicate by ticker; on conflict keep the highest-belief
     hypothesis as the provenance row.
  6. Sort by belief desc, take top `max_tickers`.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType, Hypothesis, HypothesisStatus
from app.db.models_market import Watchlist, WatchlistMember, WatchlistSource
from app.services.universe_resolver import WatchlistNotFoundError


class ResearchBuilderError(ValueError):
    """Raised when a non-research watchlist is passed to the builder."""


async def build_research_watchlist(
    session: AsyncSession,
    *,
    watchlist_id: uuid.UUID,
    evidence_window_hours: int,
    min_belief: float,
    max_tickers: int,
) -> int:
    """Replace the members of a research watchlist with the freshly-computed set.

    Returns the count of members written. Updates `last_built_at` on
    the watchlist row. Idempotent against a stable hypothesis snapshot.
    """
    watchlist = await session.scalar(
        select(Watchlist).where(Watchlist.id == watchlist_id)
    )
    if watchlist is None:
        raise WatchlistNotFoundError(f"watchlist {watchlist_id} not found")
    if watchlist.source != WatchlistSource.research.value:
        raise ResearchBuilderError(
            f"watchlist {watchlist_id} has source={watchlist.source!r}; "
            "build_research_watchlist only operates on source='research'"
        )

    cutoff = datetime.now(UTC) - timedelta(hours=evidence_window_hours)
    candidate_hypotheses = (
        await session.execute(
            select(Hypothesis)
            .where(Hypothesis.status == HypothesisStatus.active.value)
            .where(Hypothesis.last_activity_at >= cutoff)
            .where(Hypothesis.belief >= min_belief)
        )
    ).scalars().all()

    entity_id_to_hypothesis: dict[uuid.UUID, Hypothesis] = {}
    for hypothesis in candidate_hypotheses:
        for raw_id in hypothesis.scope_entity_ids:
            try:
                entity_id = uuid.UUID(raw_id)
            except (ValueError, TypeError):
                continue
            existing = entity_id_to_hypothesis.get(entity_id)
            if existing is None or (
                hypothesis.belief is not None
                and (existing.belief is None or hypothesis.belief > existing.belief)
            ):
                entity_id_to_hypothesis[entity_id] = hypothesis

    if not entity_id_to_hypothesis:
        await _replace_members(session, watchlist_id=watchlist_id, members=[])
        watchlist.last_built_at = datetime.now(UTC)
        await session.commit()
        return 0

    entities = (
        await session.execute(
            select(Entity).where(
                Entity.id.in_(list(entity_id_to_hypothesis.keys()))
            )
        )
    ).scalars().all()

    ticker_to_provenance: dict[str, Hypothesis] = {}
    for entity in entities:
        if entity.type != EntityType.company.value:
            continue
        ticker = entity.ticker_normalized
        if not ticker:
            continue
        hypothesis = entity_id_to_hypothesis[entity.id]
        existing = ticker_to_provenance.get(ticker)
        if existing is None or (
            hypothesis.belief is not None
            and (existing.belief is None or hypothesis.belief > existing.belief)
        ):
            ticker_to_provenance[ticker] = hypothesis

    ranked = sorted(
        ticker_to_provenance.items(),
        key=lambda pair: pair[1].belief or 0.0,
        reverse=True,
    )[:max_tickers]

    members: list[WatchlistMember] = []
    for ticker, hypothesis in ranked:
        last_activity_iso = (
            hypothesis.last_activity_at.isoformat()
            if hypothesis.last_activity_at is not None
            else None
        )
        members.append(
            WatchlistMember(
                id=uuid.uuid4(),
                watchlist_id=watchlist_id,
                ticker=ticker,
                hypothesis_id=hypothesis.id,
                member_metadata={
                    "belief": hypothesis.belief,
                    "last_activity_iso": last_activity_iso,
                },
            )
        )

    await _replace_members(session, watchlist_id=watchlist_id, members=members)
    watchlist.last_built_at = datetime.now(UTC)
    await session.commit()
    return len(members)


async def _replace_members(
    session: AsyncSession,
    *,
    watchlist_id: uuid.UUID,
    members: list[WatchlistMember],
) -> None:
    await session.execute(
        delete(WatchlistMember).where(
            WatchlistMember.watchlist_id == watchlist_id
        )
    )
    for member in members:
        session.add(member)


__all__ = ["ResearchBuilderError", "build_research_watchlist"]
