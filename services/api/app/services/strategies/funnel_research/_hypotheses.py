import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Hypothesis
from app.schemas.macro_brief import ProposedHypothesis
from app.services.belief import ensure_hypothesis_entity
from app.services.hypothesis import (
    DEFAULT_SIMILARITY_THRESHOLD,
    DedupAction,
    DedupOutcome,
    DuplicateConfirmer,
    Embedder,
    resolve_duplicate,
)


async def persist_hypotheses(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    proposed: list[ProposedHypothesis],
    embedder: Embedder | None = None,
    confirmer: DuplicateConfirmer | None = None,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> list[DedupOutcome]:
    """Persist proposed hypotheses with embedding-based dedup at creation.

    Each proposed claim is embedded (when an `embedder` is supplied) and
    routed through `resolve_duplicate`, which may insert, merge against an
    existing hypothesis, or supersede one. Hypotheses that are inserted or
    that supersede an existing row are mirrored as `type=hypothesis`
    entities so the belief engine can target them via
    `supports_hypothesis` / `contradicts_hypothesis` relations.

    Returns the per-claim `DedupOutcome` list. Skip-dedup callers (no
    embedder) still get an `inserted` outcome per proposed row.
    """
    outcomes: list[DedupOutcome] = []
    for item in proposed:
        embedding = await embedder.embed(item.claim_text) if embedder else None
        outcome = await resolve_duplicate(
            session=session,
            new_claim_text=item.claim_text,
            scope_entity_ids=item.scope_entity_ids,
            scope_theme_ids=[],
            proposed_by_run_id=run_id,
            embedding=embedding,
            confirmer=confirmer,
            threshold=similarity_threshold,
        )
        outcomes.append(outcome)

    fresh_ids = [
        outcome.hypothesis_id
        for outcome in outcomes
        if outcome.action is not DedupAction.merged
    ]
    if fresh_ids:
        rows = (
            (
                await session.execute(
                    select(Hypothesis).where(Hypothesis.id.in_(fresh_ids))
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            await ensure_hypothesis_entity(session=session, hypothesis=row)
    return outcomes


__all__ = ["persist_hypotheses"]
