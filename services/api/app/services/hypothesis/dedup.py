"""Hypothesis dedup at creation time (Phase 4).

A proposed claim is embedded and compared against every existing hypothesis
that already carries an embedding. Anything above the similarity threshold is
treated as a candidate; the candidates are then routed through an LLM
confirmer which returns one of:

- `duplicate`   — the new claim adds nothing; reuse the existing hypothesis.
- `supersedes`  — the new claim replaces the existing one; insert the new row
                  and mark the existing one `superseded`.
- `unrelated`   — coincidental embedding overlap; insert as a fresh row.

The flow is deliberately conservative: a missing embedding, a missing
confirmer or a confirmer that throws all collapse to "treat as new". Dedup
never silently drops a hypothesis on the basis of similarity alone.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Hypothesis, HypothesisStatus
from app.services.hypothesis.embedding import Embedder, cosine_similarity

if TYPE_CHECKING:
    from app.services.llm.client import LlmClient

DEFAULT_SIMILARITY_THRESHOLD: Final[float] = 0.85

_OPEN_STATES: Final[frozenset[str]] = frozenset(
    {HypothesisStatus.proposed.value, HypothesisStatus.active.value}
)


class DedupVerdict(StrEnum):
    duplicate = "duplicate"
    supersedes = "supersedes"
    unrelated = "unrelated"


class DedupAction(StrEnum):
    inserted = "inserted"
    merged = "merged"
    superseded = "superseded"


@dataclass(frozen=True)
class DuplicateCandidate:
    hypothesis: Hypothesis
    similarity: float


@dataclass(frozen=True)
class DedupOutcome:
    """Result of running dedup on one proposed claim.

    - `inserted`: `hypothesis_id` is the freshly-created row, `predecessor_id`
      is `None`.
    - `merged`: `hypothesis_id` is the existing row that was reused;
      `predecessor_id` is also that same row id (kept for symmetry).
    - `superseded`: `hypothesis_id` is the freshly-created row,
      `predecessor_id` is the existing row that was marked `superseded`.
    """

    action: DedupAction
    hypothesis_id: uuid.UUID
    predecessor_id: uuid.UUID | None
    similarity: float
    verdict: DedupVerdict | None


class DuplicateConfirmer(Protocol):
    async def confirm(
        self,
        *,
        new_claim_text: str,
        candidate_claim_text: str,
    ) -> DedupVerdict:
        """Return a verdict for whether the new claim duplicates / supersedes
        / is unrelated to the candidate claim."""
        ...


async def find_duplicate_candidates(
    *,
    session: AsyncSession,
    embedding: Sequence[float] | None,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    exclude_ids: Sequence[uuid.UUID] = (),
) -> list[DuplicateCandidate]:
    """Return all open hypotheses with cosine similarity above `threshold`.

    Results are sorted by similarity, descending. Hypotheses without an
    embedding or whose status is terminal (`validated`, `falsified`,
    `expired`, `superseded`) are excluded — a superseded hypothesis cannot
    itself be re-superseded, and a validated / falsified one is settled
    history.
    """
    if not embedding or threshold <= 0.0:
        return []

    rows = (
        (
            await session.execute(
                select(Hypothesis).where(
                    Hypothesis.status.in_(_OPEN_STATES),
                    Hypothesis.archived_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    excluded = {eid for eid in exclude_ids}
    candidates: list[DuplicateCandidate] = []
    for row in rows:
        if row.id in excluded:
            continue
        if row.embedding is None or not row.embedding:
            continue
        score = cosine_similarity(embedding, row.embedding)
        if score >= threshold:
            candidates.append(DuplicateCandidate(hypothesis=row, similarity=score))
    candidates.sort(key=lambda c: c.similarity, reverse=True)
    return candidates


async def resolve_duplicate(
    *,
    session: AsyncSession,
    new_claim_text: str,
    scope_entity_ids: Sequence[uuid.UUID],
    scope_theme_ids: Sequence[uuid.UUID],
    proposed_by_run_id: uuid.UUID | None,
    embedding: Sequence[float] | None,
    confirmer: DuplicateConfirmer | None,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    now: datetime | None = None,
) -> DedupOutcome:
    """Run dedup for one proposed claim and return the resolved outcome.

    Either inserts a new `Hypothesis` row (always, unless dedup decides
    otherwise) or merges/supersedes against an existing row.

    The `Hypothesis` mirror `Entity` is not created here — callers should
    invoke `ensure_hypothesis_entity` on the returned row after dedup is
    resolved, so the entity mirror is always in lockstep with the canonical
    row (and not duplicated when dedup merges).
    """
    candidates = await find_duplicate_candidates(
        session=session,
        embedding=embedding,
        threshold=threshold,
    )
    verdict, picked = await _confirm_with_llm(
        new_claim_text=new_claim_text,
        candidates=candidates,
        confirmer=confirmer,
    )
    effective_now = now if now is not None else datetime.now(UTC)

    if verdict is DedupVerdict.duplicate and picked is not None:
        return DedupOutcome(
            action=DedupAction.merged,
            hypothesis_id=picked.hypothesis.id,
            predecessor_id=picked.hypothesis.id,
            similarity=picked.similarity,
            verdict=verdict,
        )

    new_row = _build_hypothesis(
        claim_text=new_claim_text,
        scope_entity_ids=scope_entity_ids,
        scope_theme_ids=scope_theme_ids,
        proposed_by_run_id=proposed_by_run_id,
        embedding=embedding,
        last_activity_at=effective_now,
    )
    session.add(new_row)
    await session.flush()

    if verdict is DedupVerdict.supersedes and picked is not None:
        picked.hypothesis.status = HypothesisStatus.superseded.value
        picked.hypothesis.superseded_by_id = new_row.id
        picked.hypothesis.archived_at = effective_now
        picked.hypothesis.archived_reason = "superseded"
        return DedupOutcome(
            action=DedupAction.superseded,
            hypothesis_id=new_row.id,
            predecessor_id=picked.hypothesis.id,
            similarity=picked.similarity,
            verdict=verdict,
        )

    return DedupOutcome(
        action=DedupAction.inserted,
        hypothesis_id=new_row.id,
        predecessor_id=None,
        similarity=picked.similarity if picked is not None else 0.0,
        verdict=verdict,
    )


async def _confirm_with_llm(
    *,
    new_claim_text: str,
    candidates: Sequence[DuplicateCandidate],
    confirmer: DuplicateConfirmer | None,
) -> tuple[DedupVerdict | None, DuplicateCandidate | None]:
    """Walk the candidate list (highest similarity first) until the LLM
    returns a verdict that triggers an action.

    Stops on the first `duplicate` or `supersedes`. A confirmer that throws
    is treated as "unrelated" for that candidate — dedup never silently
    swallows an exception; the caller surfaces the new row instead.
    """
    if not candidates:
        return None, None
    if confirmer is None:
        return DedupVerdict.unrelated, candidates[0]

    last_unrelated: DuplicateCandidate | None = None
    for candidate in candidates:
        try:
            verdict = await confirmer.confirm(
                new_claim_text=new_claim_text,
                candidate_claim_text=candidate.hypothesis.claim_text,
            )
        except Exception:
            verdict = DedupVerdict.unrelated
        if verdict is DedupVerdict.duplicate or verdict is DedupVerdict.supersedes:
            return verdict, candidate
        last_unrelated = candidate
    return DedupVerdict.unrelated, last_unrelated


def _build_hypothesis(
    *,
    claim_text: str,
    scope_entity_ids: Sequence[uuid.UUID],
    scope_theme_ids: Sequence[uuid.UUID],
    proposed_by_run_id: uuid.UUID | None,
    embedding: Sequence[float] | None,
    last_activity_at: datetime,
) -> Hypothesis:
    return Hypothesis(
        claim_text=claim_text,
        scope_entity_ids=[str(eid) for eid in scope_entity_ids],
        scope_theme_ids=[str(tid) for tid in scope_theme_ids],
        status=HypothesisStatus.proposed.value,
        valid_until=None,
        proposed_by_run_id=proposed_by_run_id,
        belief=None,
        belief_history=[],
        embedding=list(embedding) if embedding is not None else None,
        last_activity_at=last_activity_at,
    )


DEDUP_PROMPT_VERSION: Final[str] = "hypothesis-dedup-v1"
DEDUP_MODEL_DEFAULT: Final[str] = "gpt-5-mini"

_DEDUP_SYSTEM_PROMPT: Final[str] = (
    "You compare two research hypotheses for an investment research desk. "
    "Return exactly one word: 'duplicate', 'supersedes', or 'unrelated'. "
    "'duplicate' = same meaning, no new information. "
    "'supersedes' = the new claim refines or replaces the existing one with "
    "a sharper / better-evidenced framing. "
    "'unrelated' = coincidental overlap; the claims address different things."
)


@dataclass(frozen=True)
class OpenAiDuplicateConfirmer:
    """`LlmClient`-backed dedup confirmer.

    The confirmer is bound to a specific session + run so the underlying
    `LlmClient.complete` call is fully observable: it lands in
    `llm_call_logs` with `stage='hypothesis_dedup'`, `agent_name='dedup'`,
    `prompt_version='hypothesis-dedup-v1'`, and counts against the per-run
    budget. A response that does not begin with `duplicate` or `supersede`
    is treated as `unrelated` so a parse miss never silently merges.
    """

    llm_client: LlmClient
    session: AsyncSession
    run_id: uuid.UUID | None = None
    model: str = DEDUP_MODEL_DEFAULT
    prompt_version: str = DEDUP_PROMPT_VERSION

    async def confirm(
        self,
        *,
        new_claim_text: str,
        candidate_claim_text: str,
    ) -> DedupVerdict:
        from app.services.llm.client import LlmMessage

        user_prompt = (
            f"New claim: {new_claim_text}\n"
            f"Existing claim: {candidate_claim_text}\n\n"
            "Respond with exactly one word: duplicate, supersedes, or unrelated."
        )
        result = await self.llm_client.complete(
            session=self.session,
            messages=[
                LlmMessage(role="system", content=_DEDUP_SYSTEM_PROMPT),
                LlmMessage(role="user", content=user_prompt),
            ],
            model=self.model,
            run_id=self.run_id,
            prompt_version=self.prompt_version,
            stage="hypothesis_dedup",
            agent_name="dedup",
            temperature=0.0,
        )
        return _parse_verdict(result.content)


def _parse_verdict(content: str) -> DedupVerdict:
    token = content.strip().lower().split()[:1]
    if not token:
        return DedupVerdict.unrelated
    head = token[0].rstrip(".,!?:;\"'")
    if head == "duplicate":
        return DedupVerdict.duplicate
    if head.startswith("supersed"):
        return DedupVerdict.supersedes
    return DedupVerdict.unrelated


__all__ = [
    "DEDUP_MODEL_DEFAULT",
    "DEDUP_PROMPT_VERSION",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "DedupAction",
    "DedupOutcome",
    "DedupVerdict",
    "DuplicateCandidate",
    "DuplicateConfirmer",
    "Embedder",
    "OpenAiDuplicateConfirmer",
    "find_duplicate_candidates",
    "resolve_duplicate",
]
