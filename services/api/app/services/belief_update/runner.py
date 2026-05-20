"""Belief-update pass: select → call LLM per hypothesis → write Relation rows
→ recompute belief via Phase 3 trigger.

Per-hypothesis LLM calls run sequentially, each in its own session, mirroring
the pattern that resolved Phase 5 bugs #1 and #2 (concurrent shared-session
extraction corrupted state). Per-hypothesis errors are warn events; only
budget halts abort the stage.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models_graph import (
    Hypothesis,
    Relation,
    RelationType,
)
from app.db.models_runs import RunEventLevel
from app.services.belief.trigger import recompute_beliefs_for_relations
from app.services.belief_update.prompt import (
    PROMPT_VERSION,
    BeliefUpdateResponse,
    BeliefUpdateVerdict,
    build_belief_update_messages,
)
from app.services.belief_update.selector import (
    BeliefUpdateCandidate,
    select_belief_update_inputs,
)
from app.services.llm import (
    BudgetKilledError,
    BudgetPausedError,
    LlmClient,
)
from app.services.run_events import emit_run_event
from app.services.run_orchestrator import RunOrchestrator

STAGE = "belief_update"
AGENT = "belief_update"
_HIGH_CONFIDENCE_THRESHOLD = 0.7


class BeliefUpdateError(Exception):
    """Raised when the belief-update pass cannot complete."""


class BeliefUpdateBudgetHaltError(BeliefUpdateError):
    """Raised when a budget pause/kill aborts the stage. Pause/fail has
    already been routed through orchestrator before this is raised."""


@dataclass(frozen=True)
class BeliefUpdateOutcome:
    hypothesis_count: int
    chunks_judged: int
    relations_written: int
    recomputed_hypothesis_ids: list[uuid.UUID]


class _PerHypothesisError(Exception):
    """Recoverable per-hypothesis failure that becomes a warn event."""


async def run_belief_update_pass(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    llm_client: LlmClient,
    orchestrator: RunOrchestrator,
    max_chunks_per_hypothesis: int | None = None,
) -> BeliefUpdateOutcome:
    settings = get_settings()
    cap = (
        max_chunks_per_hypothesis
        if max_chunks_per_hypothesis is not None
        else settings.belief_update_max_chunks_per_hypothesis
    )

    async with session_factory() as selector_session:
        candidates = await select_belief_update_inputs(
            session=selector_session,
            run_id=run_id,
            max_chunks_per_hypothesis=cap,
        )

    if not candidates:
        return BeliefUpdateOutcome(
            hypothesis_count=0,
            chunks_judged=0,
            relations_written=0,
            recomputed_hypothesis_ids=[],
        )

    all_relation_ids: list[uuid.UUID] = []
    chunks_judged = 0

    for candidate in candidates:
        if not candidate.chunks:
            async with session_factory() as session:
                _emit_warn(
                    session,
                    run_id=run_id,
                    hypothesis_id=candidate.hypothesis.id,
                    reason="no chunks in scope after idempotency filter",
                )
                await session.commit()
            continue

        async with session_factory() as session:
            try:
                verdicts = await _call_belief_update_llm(
                    session=session,
                    run_id=run_id,
                    candidate=candidate,
                    llm_client=llm_client,
                    model=settings.belief_update_model,
                )
            except BudgetPausedError as exc:
                await orchestrator.pause(run_id=run_id, reason=str(exc))
                raise BeliefUpdateBudgetHaltError(
                    "belief_update paused by budget guard"
                ) from exc
            except BudgetKilledError as exc:
                await orchestrator.fail(run_id=run_id, reason=str(exc))
                raise BeliefUpdateBudgetHaltError(
                    "belief_update killed by budget guard"
                ) from exc
            except _PerHypothesisError as exc:
                _emit_warn(
                    session,
                    run_id=run_id,
                    hypothesis_id=candidate.hypothesis.id,
                    reason=str(exc),
                )
                await session.commit()
                continue
            chunks_judged += len(candidate.chunks)
            new_ids = _write_relations(
                session=session,
                candidate=candidate,
                verdicts=verdicts,
                model_id=settings.belief_update_model,
            )
            await session.commit()
            all_relation_ids.extend(new_ids)

    recomputed_ids: list[uuid.UUID] = []
    if all_relation_ids:
        async with session_factory() as session:
            results = await recompute_beliefs_for_relations(
                session=session, relation_ids=all_relation_ids
            )
            recomputed_ids = list(results.keys())
            await session.commit()

    async with session_factory() as session:
        emit_run_event(
            session,
            run_id=run_id,
            level=RunEventLevel.info,
            message=(
                f"belief_update completed: "
                f"hypotheses={len(candidates)} chunks_judged={chunks_judged} "
                f"relations_written={len(all_relation_ids)}"
            ),
            data={
                "event": "belief_update_completed",
                "hypothesis_count": len(candidates),
                "chunks_judged": chunks_judged,
                "relations_written": len(all_relation_ids),
            },
        )
        await session.commit()

    return BeliefUpdateOutcome(
        hypothesis_count=len(candidates),
        chunks_judged=chunks_judged,
        relations_written=len(all_relation_ids),
        recomputed_hypothesis_ids=recomputed_ids,
    )


async def _call_belief_update_llm(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    candidate: BeliefUpdateCandidate,
    llm_client: LlmClient,
    model: str,
) -> list[BeliefUpdateVerdict]:
    chunks_in = [(chunk.id, chunk.text) for chunk in candidate.chunks]
    messages = build_belief_update_messages(
        claim_text=candidate.hypothesis.claim_text,
        chunks=chunks_in,
    )
    try:
        response = await llm_client.complete(
            session=session,
            run_id=run_id,
            model=model,
            messages=messages,
            prompt_version=PROMPT_VERSION,
            stage=STAGE,
            agent_name=AGENT,
            temperature=0.0,
        )
    except (BudgetPausedError, BudgetKilledError):
        raise
    except Exception as exc:
        raise _PerHypothesisError(f"llm call failed: {exc}") from exc

    try:
        payload = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise _PerHypothesisError(f"llm returned non-json: {exc}") from exc

    try:
        validated = BeliefUpdateResponse.model_validate(payload)
    except ValidationError as exc:
        raise _PerHypothesisError(f"llm json failed schema: {exc}") from exc

    chunk_id_set = {chunk.id for chunk in candidate.chunks}
    return [v for v in validated.verdicts if v.chunk_id in chunk_id_set]


def _write_relations(
    *,
    session: AsyncSession,
    candidate: BeliefUpdateCandidate,
    verdicts: list[BeliefUpdateVerdict],
    model_id: str,
) -> list[uuid.UUID]:
    hypothesis = candidate.hypothesis
    hypothesis_entity_id = hypothesis.entity_id
    if hypothesis_entity_id is None:
        raise RuntimeError(
            "belief_update.runner._write_relations called with hypothesis whose "
            "entity_id is None; selector should have filtered it"
        )
    from_id = _from_id_for_hypothesis(
        hypothesis, fallback=hypothesis_entity_id
    )
    chunk_by_id = {chunk.id: chunk for chunk in candidate.chunks}
    written: list[uuid.UUID] = []
    for verdict in verdicts:
        if verdict.verdict == "unrelated":
            continue
        chunk = chunk_by_id.get(verdict.chunk_id)
        if chunk is None:
            continue
        relation_type = (
            RelationType.supports_hypothesis.value
            if verdict.verdict == "supports"
            else RelationType.contradicts_hypothesis.value
        )
        sign = 1.0 if verdict.verdict == "supports" else -1.0
        is_explicit = verdict.confidence >= _HIGH_CONFIDENCE_THRESHOLD
        relation_id = uuid.uuid4()
        relation = Relation(
            id=relation_id,
            from_id=from_id,
            to_id=hypothesis_entity_id,
            type=relation_type,
            chunk_id=chunk.id,
            source_id=chunk.evidence_id,
            quote=verdict.quote,
            relevance=verdict.confidence,
            extraction_confidence=verdict.confidence,
            is_explicit=is_explicit,
            sign=sign,
            prompt_version=PROMPT_VERSION,
            extracted_by_model=model_id,
            attributes={
                "verdict": verdict.verdict,
                "confidence": verdict.confidence,
            },
        )
        session.add(relation)
        written.append(relation_id)
    return written


def _from_id_for_hypothesis(
    hypothesis: Hypothesis, *, fallback: uuid.UUID
) -> uuid.UUID:
    """Resolve Relation.from_id for a belief relation.

    `Relation.from_id` is NOT NULL but the belief engine only indexes by
    `to_id`. Use the first scope entity for semantic value; fall back to
    a self-loop on the hypothesis mirror when scope is empty (macro-only
    hypotheses).
    """
    if hypothesis.scope_entity_ids:
        return uuid.UUID(hypothesis.scope_entity_ids[0])
    return fallback


def _emit_warn(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    hypothesis_id: uuid.UUID,
    reason: str,
) -> None:
    emit_run_event(
        session,
        run_id=run_id,
        level=RunEventLevel.warn,
        message=f"belief_update per-hypothesis failure {hypothesis_id!s}: {reason}",
        data={
            "event": "belief_update_per_hypothesis_failure",
            "hypothesis_id": str(hypothesis_id),
            "reason": reason,
        },
    )


__all__ = [
    "BeliefUpdateBudgetHaltError",
    "BeliefUpdateError",
    "BeliefUpdateOutcome",
    "run_belief_update_pass",
]
