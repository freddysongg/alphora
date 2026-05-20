import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Hypothesis, HypothesisStatus
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.schemas.budget import TokenUsage
from app.services.hypothesis.dedup import (
    DedupAction,
    DedupVerdict,
    DuplicateConfirmer,
    OpenAiDuplicateConfirmer,
    _parse_verdict,
    find_duplicate_candidates,
    resolve_duplicate,
)
from app.services.llm.client import LlmCompletionResult, LlmMessage


class _FixedConfirmer:
    def __init__(self, verdict: DedupVerdict) -> None:
        self._verdict = verdict
        self.calls: list[tuple[str, str]] = []

    async def confirm(
        self,
        *,
        new_claim_text: str,
        candidate_claim_text: str,
    ) -> DedupVerdict:
        self.calls.append((new_claim_text, candidate_claim_text))
        return self._verdict


class _SequenceConfirmer:
    def __init__(self, verdicts: list[DedupVerdict]) -> None:
        self._verdicts = list(verdicts)
        self.calls: list[tuple[str, str]] = []

    async def confirm(
        self,
        *,
        new_claim_text: str,
        candidate_claim_text: str,
    ) -> DedupVerdict:
        self.calls.append((new_claim_text, candidate_claim_text))
        return self._verdicts.pop(0)


class _RaisingConfirmer:
    async def confirm(
        self,
        *,
        new_claim_text: str,
        candidate_claim_text: str,
    ) -> DedupVerdict:
        raise RuntimeError("llm exploded")


async def _seed(
    session: AsyncSession,
    *,
    claim_text: str,
    embedding: list[float] | None,
    status_value: str = HypothesisStatus.active.value,
) -> Hypothesis:
    row = Hypothesis(
        claim_text=claim_text,
        scope_entity_ids=[],
        scope_theme_ids=[],
        status=status_value,
        embedding=embedding,
    )
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_find_candidates_returns_empty_when_no_embedding(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session, claim_text="abc", embedding=[1.0, 0.0])
    await db_session.commit()
    assert (
        await find_duplicate_candidates(session=db_session, embedding=None)
    ) == []


@pytest.mark.asyncio
async def test_find_candidates_skips_rows_without_embedding(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session, claim_text="no embedding", embedding=None)
    await db_session.commit()
    out = await find_duplicate_candidates(
        session=db_session, embedding=[1.0, 0.0]
    )
    assert out == []


@pytest.mark.asyncio
async def test_find_candidates_above_threshold_only(
    db_session: AsyncSession,
) -> None:
    near = await _seed(
        db_session, claim_text="near", embedding=[1.0, 0.0]
    )
    far = await _seed(
        db_session, claim_text="far", embedding=[0.0, 1.0]
    )
    await db_session.commit()
    out = await find_duplicate_candidates(
        session=db_session, embedding=[1.0, 0.0], threshold=0.85
    )
    ids = [candidate.hypothesis.id for candidate in out]
    assert near.id in ids
    assert far.id not in ids


@pytest.mark.asyncio
async def test_find_candidates_excludes_terminal_states(
    db_session: AsyncSession,
) -> None:
    await _seed(
        db_session,
        claim_text="settled",
        embedding=[1.0, 0.0],
        status_value=HypothesisStatus.validated.value,
    )
    await _seed(
        db_session,
        claim_text="settled bad",
        embedding=[1.0, 0.0],
        status_value=HypothesisStatus.falsified.value,
    )
    await db_session.commit()
    out = await find_duplicate_candidates(
        session=db_session, embedding=[1.0, 0.0]
    )
    assert out == []


@pytest.mark.asyncio
async def test_find_candidates_sorted_by_similarity_descending(
    db_session: AsyncSession,
) -> None:
    perfect = await _seed(
        db_session, claim_text="perfect match", embedding=[1.0, 0.0]
    )
    close = await _seed(
        db_session,
        claim_text="close match",
        embedding=[0.9659, 0.2588],
    )
    await db_session.commit()
    out = await find_duplicate_candidates(
        session=db_session, embedding=[1.0, 0.0], threshold=0.85
    )
    assert [candidate.hypothesis.id for candidate in out] == [perfect.id, close.id]


@pytest.mark.asyncio
async def test_resolve_duplicate_inserts_when_no_candidates(
    db_session: AsyncSession,
) -> None:
    confirmer = _FixedConfirmer(DedupVerdict.unrelated)
    outcome = await resolve_duplicate(
        session=db_session,
        new_claim_text="brand new",
        scope_entity_ids=[],
        scope_theme_ids=[],
        proposed_by_run_id=None,
        embedding=[1.0, 0.0],
        confirmer=confirmer,
    )
    await db_session.commit()
    assert outcome.action is DedupAction.inserted
    assert outcome.predecessor_id is None
    assert outcome.verdict is None
    assert confirmer.calls == []
    row = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == outcome.hypothesis_id)
        )
    ).scalar_one()
    assert row.claim_text == "brand new"
    assert row.embedding == [1.0, 0.0]


@pytest.mark.asyncio
async def test_resolve_duplicate_merges_on_duplicate_verdict(
    db_session: AsyncSession,
) -> None:
    existing = await _seed(
        db_session, claim_text="energy outperforms", embedding=[1.0, 0.0]
    )
    await db_session.commit()
    confirmer = _FixedConfirmer(DedupVerdict.duplicate)
    outcome = await resolve_duplicate(
        session=db_session,
        new_claim_text="energy outperforms again",
        scope_entity_ids=[],
        scope_theme_ids=[],
        proposed_by_run_id=None,
        embedding=[1.0, 0.0],
        confirmer=confirmer,
    )
    await db_session.commit()
    assert outcome.action is DedupAction.merged
    assert outcome.hypothesis_id == existing.id
    assert outcome.predecessor_id == existing.id
    assert outcome.verdict is DedupVerdict.duplicate
    assert len(confirmer.calls) == 1
    rows = (
        (await db_session.execute(select(Hypothesis))).scalars().all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_resolve_duplicate_supersedes_when_verdict_supersedes(
    db_session: AsyncSession,
) -> None:
    old = await _seed(
        db_session, claim_text="old claim", embedding=[1.0, 0.0]
    )
    await db_session.commit()
    confirmer = _FixedConfirmer(DedupVerdict.supersedes)
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    outcome = await resolve_duplicate(
        session=db_session,
        new_claim_text="newer sharper claim",
        scope_entity_ids=[],
        scope_theme_ids=[],
        proposed_by_run_id=None,
        embedding=[1.0, 0.0],
        confirmer=confirmer,
        now=now,
    )
    await db_session.commit()
    assert outcome.action is DedupAction.superseded
    assert outcome.predecessor_id == old.id
    assert outcome.verdict is DedupVerdict.supersedes
    successor = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == outcome.hypothesis_id)
        )
    ).scalar_one()
    assert successor.claim_text == "newer sharper claim"
    refreshed_old = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == old.id)
        )
    ).scalar_one()
    assert refreshed_old.status == HypothesisStatus.superseded.value
    assert refreshed_old.superseded_by_id == successor.id
    assert refreshed_old.archived_reason == "superseded"
    assert refreshed_old.archived_at == now


@pytest.mark.asyncio
async def test_resolve_duplicate_inserts_on_unrelated_with_high_similarity(
    db_session: AsyncSession,
) -> None:
    await _seed(
        db_session, claim_text="similar but different", embedding=[1.0, 0.0]
    )
    await db_session.commit()
    confirmer = _FixedConfirmer(DedupVerdict.unrelated)
    outcome = await resolve_duplicate(
        session=db_session,
        new_claim_text="similar but different too",
        scope_entity_ids=[],
        scope_theme_ids=[],
        proposed_by_run_id=None,
        embedding=[1.0, 0.0],
        confirmer=confirmer,
    )
    await db_session.commit()
    assert outcome.action is DedupAction.inserted
    assert outcome.verdict is DedupVerdict.unrelated
    rows = (
        (await db_session.execute(select(Hypothesis))).scalars().all()
    )
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_resolve_duplicate_inserts_when_confirmer_is_none(
    db_session: AsyncSession,
) -> None:
    await _seed(
        db_session, claim_text="existing", embedding=[1.0, 0.0]
    )
    await db_session.commit()
    outcome = await resolve_duplicate(
        session=db_session,
        new_claim_text="should still insert without confirmer",
        scope_entity_ids=[],
        scope_theme_ids=[],
        proposed_by_run_id=None,
        embedding=[1.0, 0.0],
        confirmer=None,
    )
    await db_session.commit()
    assert outcome.action is DedupAction.inserted
    assert outcome.verdict is DedupVerdict.unrelated


@pytest.mark.asyncio
async def test_resolve_duplicate_walks_to_next_candidate_on_unrelated(
    db_session: AsyncSession,
) -> None:
    top = await _seed(
        db_session, claim_text="top similarity", embedding=[1.0, 0.0]
    )
    second = await _seed(
        db_session,
        claim_text="second similarity",
        embedding=[0.9659, 0.2588],
    )
    await db_session.commit()
    confirmer = _SequenceConfirmer(
        [DedupVerdict.unrelated, DedupVerdict.duplicate]
    )
    outcome = await resolve_duplicate(
        session=db_session,
        new_claim_text="probe",
        scope_entity_ids=[],
        scope_theme_ids=[],
        proposed_by_run_id=None,
        embedding=[1.0, 0.0],
        confirmer=confirmer,
    )
    await db_session.commit()
    assert outcome.action is DedupAction.merged
    assert outcome.hypothesis_id == second.id
    assert outcome.predecessor_id == second.id
    assert len(confirmer.calls) == 2
    assert top is not None


@pytest.mark.asyncio
async def test_resolve_duplicate_treats_confirmer_errors_as_unrelated(
    db_session: AsyncSession,
) -> None:
    await _seed(
        db_session, claim_text="will throw", embedding=[1.0, 0.0]
    )
    await db_session.commit()
    confirmer: DuplicateConfirmer = _RaisingConfirmer()
    outcome = await resolve_duplicate(
        session=db_session,
        new_claim_text="new",
        scope_entity_ids=[],
        scope_theme_ids=[],
        proposed_by_run_id=None,
        embedding=[1.0, 0.0],
        confirmer=confirmer,
    )
    await db_session.commit()
    assert outcome.action is DedupAction.inserted


@pytest.mark.asyncio
async def test_resolve_duplicate_persists_scope_and_run_id_on_new(
    db_session: AsyncSession,
) -> None:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 20),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
    )
    db_session.add(run)
    await db_session.flush()
    entity_a = uuid.uuid4()
    entity_b = uuid.uuid4()
    theme_a = uuid.uuid4()
    outcome = await resolve_duplicate(
        session=db_session,
        new_claim_text="claim with scope",
        scope_entity_ids=[entity_a, entity_b],
        scope_theme_ids=[theme_a],
        proposed_by_run_id=run.id,
        embedding=[1.0, 0.0],
        confirmer=None,
    )
    await db_session.commit()
    row = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == outcome.hypothesis_id)
        )
    ).scalar_one()
    assert row.scope_entity_ids == [str(entity_a), str(entity_b)]
    assert row.scope_theme_ids == [str(theme_a)]
    assert row.proposed_by_run_id == run.id
    assert row.last_activity_at is not None


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("duplicate", DedupVerdict.duplicate),
        ("DUPLICATE", DedupVerdict.duplicate),
        ("Duplicate.", DedupVerdict.duplicate),
        ("supersedes", DedupVerdict.supersedes),
        ("supersede", DedupVerdict.supersedes),
        ("Supersedes.", DedupVerdict.supersedes),
        ("unrelated", DedupVerdict.unrelated),
        ("not sure", DedupVerdict.unrelated),
        ("", DedupVerdict.unrelated),
        ("   \n\t", DedupVerdict.unrelated),
    ],
)
def test_parse_verdict_handles_common_response_shapes(
    content: str, expected: DedupVerdict
) -> None:
    assert _parse_verdict(content) is expected


class _RecordingLlmClient:
    """Captures the args passed to `LlmClient.complete` and returns a
    canned content string. Mirrors the small subset of the real client
    that `OpenAiDuplicateConfirmer` exercises."""

    def __init__(self, response_content: str) -> None:
        self.response_content = response_content
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        session: AsyncSession,
        messages: Sequence[LlmMessage],
        model: str,
        run_id: uuid.UUID | None = None,
        evidence_ids: Sequence[str] | None = None,
        prompt_version: str | None = None,
        stage: str | None = None,
        agent_name: str | None = None,
        temperature: float | None = None,
        seed: int | None = None,
        reasoning_effort: str | None = None,
    ) -> LlmCompletionResult:
        self.calls.append(
            {
                "messages": list(messages),
                "model": model,
                "run_id": run_id,
                "prompt_version": prompt_version,
                "stage": stage,
                "agent_name": agent_name,
                "temperature": temperature,
            }
        )
        return LlmCompletionResult(
            content=self.response_content,
            model=model,
            usage=TokenUsage(),
            cost_usd=Decimal("0"),
            latency_ms=1,
            log_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_openai_confirmer_returns_duplicate_when_model_says_so(
    db_session: AsyncSession,
) -> None:
    llm_client = _RecordingLlmClient("duplicate")
    confirmer = OpenAiDuplicateConfirmer(
        llm_client=llm_client,
        session=db_session,
    )
    verdict = await confirmer.confirm(
        new_claim_text="oil rallies on supply cut",
        candidate_claim_text="oil rallies on opec supply cut",
    )
    assert verdict is DedupVerdict.duplicate
    assert len(llm_client.calls) == 1
    call = llm_client.calls[0]
    assert call["stage"] == "hypothesis_dedup"
    assert call["agent_name"] == "dedup"
    assert call["prompt_version"] == "hypothesis-dedup-v1"
    assert call["temperature"] == 0.0
    payload = "\n".join(message.content for message in call["messages"])
    assert "oil rallies on supply cut" in payload
    assert "oil rallies on opec supply cut" in payload


@pytest.mark.asyncio
async def test_openai_confirmer_falls_back_to_unrelated_on_ambiguous_text(
    db_session: AsyncSession,
) -> None:
    llm_client = _RecordingLlmClient("possibly related but not the same")
    confirmer = OpenAiDuplicateConfirmer(
        llm_client=llm_client,
        session=db_session,
    )
    verdict = await confirmer.confirm(
        new_claim_text="new",
        candidate_claim_text="candidate",
    )
    assert verdict is DedupVerdict.unrelated


@pytest.mark.asyncio
async def test_openai_confirmer_recognises_supersedes_word_form(
    db_session: AsyncSession,
) -> None:
    llm_client = _RecordingLlmClient("supersedes — refines the original framing")
    confirmer = OpenAiDuplicateConfirmer(
        llm_client=llm_client,
        session=db_session,
    )
    verdict = await confirmer.confirm(
        new_claim_text="new framing",
        candidate_claim_text="old framing",
    )
    assert verdict is DedupVerdict.supersedes


def test_dedup_model_default_resolves_to_high_tier() -> None:
    from app.config import get_settings
    from app.services.hypothesis.dedup import DEDUP_MODEL_DEFAULT

    assert DEDUP_MODEL_DEFAULT == get_settings().model_tier_high
