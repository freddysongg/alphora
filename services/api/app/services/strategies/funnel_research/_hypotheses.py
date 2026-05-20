import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Hypothesis, HypothesisStatus
from app.schemas.macro_brief import ProposedHypothesis
from app.services.belief import ensure_hypothesis_entity


async def persist_hypotheses(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    proposed: list[ProposedHypothesis],
) -> list[uuid.UUID]:
    created: list[Hypothesis] = []
    for item in proposed:
        row = Hypothesis(
            claim_text=item.claim_text,
            scope_entity_ids=[str(eid) for eid in item.scope_entity_ids],
            scope_theme_ids=[],
            status=HypothesisStatus.proposed.value,
            valid_until=None,
            proposed_by_run_id=run_id,
            belief=None,
            belief_history=[],
        )
        session.add(row)
        created.append(row)
    await session.flush()

    for row in created:
        await ensure_hypothesis_entity(session=session, hypothesis=row)
    return [row.id for row in created]


__all__ = ["persist_hypotheses"]
