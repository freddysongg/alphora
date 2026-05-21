import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Hypothesis
from app.db.models_runs import RunEventLevel
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
from app.services.run_events import emit_run_event


async def _embed_or_warn(
    *,
    embedder: Embedder | None,
    claim_text: str,
    session: AsyncSession,
    run_id: uuid.UUID,
) -> list[float] | None:
    """Embed a claim, degrading to `None` on transient embedder failure.

    The dedup pipeline already treats `embedding=None` as "no candidates"
    and inserts a fresh row, so the safe degrade is to skip dedup for this
    claim rather than fail the whole macro run after synthesis. A warn
    event records the failure so the operator can investigate.
    """
    if embedder is None:
        return None
    try:
        return list(await embedder.embed(claim_text))
    except Exception as exc:
        emit_run_event(
            session,
            run_id=run_id,
            level=RunEventLevel.warn,
            message=f"hypothesis embedding failed, inserting without dedup: {exc}",
            data={
                "event": "hypothesis_embedding_failure",
                "reason": str(exc),
            },
        )
        return None


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

    A transient embedder failure does not abort the run: the claim is
    inserted without dedup and a warn event is emitted. This matches the
    documented dedup contract that `embedding=None` collapses to "treat
    as new".

    Returns the per-claim `DedupOutcome` list. Skip-dedup callers (no
    embedder) still get an `inserted` outcome per proposed row.
    """
    outcomes: list[DedupOutcome] = []
    for item in proposed:
        embedding = await _embed_or_warn(
            embedder=embedder,
            claim_text=item.claim_text,
            session=session,
            run_id=run_id,
        )
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
