import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType, Hypothesis, HypothesisStatus
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.schemas.macro_brief import ProposedHypothesis
from app.services.hypothesis.dedup import DedupAction, DedupVerdict


async def _make_run(session: AsyncSession) -> uuid.UUID:
    from datetime import date

    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
    )
    session.add(run)
    await session.flush()
    return run.id


class _FixedEmbedder:
    """Returns the same vector every time — useful for forcing collisions
    in dedup tests."""

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector

    async def embed(self, text: str) -> list[float]:
        return list(self._vector)


class _DistinctEmbedder:
    """Hashes the input text to produce a deterministic but per-text
    embedding, so distinct claims do not look like duplicates."""

    async def embed(self, text: str) -> list[float]:
        seed = sum(ord(ch) for ch in text)
        return [
            float(((seed * 7) % 1000) / 1000.0),
            float(((seed * 11) % 1000) / 1000.0),
        ]


class _FixedConfirmer:
    def __init__(self, verdict: DedupVerdict) -> None:
        self._verdict = verdict

    async def confirm(
        self,
        *,
        new_claim_text: str,
        candidate_claim_text: str,
    ) -> DedupVerdict:
        return self._verdict


@pytest.mark.asyncio
async def test_proposed_hypothesis_writes_hypothesis_row(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research._hypotheses import persist_hypotheses

    run_id = await _make_run(db_session)
    scope_eid = uuid.uuid4()
    proposed = [
        ProposedHypothesis(
            claim_text="Energy outperforms",
            scope_entity_ids=[scope_eid],
            evidence_ids=[uuid.uuid4()],
        )
    ]
    outcomes = await persist_hypotheses(
        session=db_session, run_id=run_id, proposed=proposed
    )
    await db_session.commit()
    assert len(outcomes) == 1
    assert outcomes[0].action is DedupAction.inserted

    row = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == outcomes[0].hypothesis_id)
        )
    ).scalar_one()
    assert row.claim_text == "Energy outperforms"
    assert row.scope_entity_ids == [str(scope_eid)]
    assert row.scope_theme_ids == []
    assert row.status == HypothesisStatus.proposed.value
    assert row.proposed_by_run_id == run_id
    assert row.belief is None


@pytest.mark.asyncio
async def test_empty_proposed_writes_zero_rows(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research._hypotheses import persist_hypotheses

    run_id = await _make_run(db_session)
    outcomes = await persist_hypotheses(
        session=db_session, run_id=run_id, proposed=[]
    )
    await db_session.commit()
    assert outcomes == []


@pytest.mark.asyncio
async def test_persist_hypothesis_mirrors_entity_and_writes_entity_id(
    db_session: AsyncSession,
) -> None:
    from app.services.strategies.funnel_research._hypotheses import persist_hypotheses

    run_id = await _make_run(db_session)
    proposed = [
        ProposedHypothesis(
            claim_text="Capex tightens",
            scope_entity_ids=[uuid.uuid4()],
            evidence_ids=[uuid.uuid4()],
        )
    ]
    outcomes = await persist_hypotheses(
        session=db_session, run_id=run_id, proposed=proposed
    )
    await db_session.commit()

    hypothesis = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == outcomes[0].hypothesis_id)
        )
    ).scalar_one()
    assert hypothesis.entity_id is not None

    entity = (
        await db_session.execute(
            select(Entity).where(Entity.id == hypothesis.entity_id)
        )
    ).scalar_one()
    assert entity.type == EntityType.hypothesis.value
    assert entity.canonical_name == "Capex tightens"
    assert entity.external_ids == {"hypothesis_id": str(hypothesis.id)}


@pytest.mark.asyncio
async def test_persist_hypotheses_dedups_against_existing_active(
    db_session: AsyncSession,
) -> None:
    from app.services.strategies.funnel_research._hypotheses import persist_hypotheses

    run_id = await _make_run(db_session)
    existing = Hypothesis(
        claim_text="Energy outperforms",
        scope_entity_ids=[],
        scope_theme_ids=[],
        status=HypothesisStatus.active.value,
        embedding=[1.0, 0.0],
    )
    db_session.add(existing)
    await db_session.flush()
    await db_session.commit()

    proposed = [
        ProposedHypothesis(
            claim_text="Energy keeps outperforming",
            scope_entity_ids=[],
            evidence_ids=[],
        )
    ]
    outcomes = await persist_hypotheses(
        session=db_session,
        run_id=run_id,
        proposed=proposed,
        embedder=_FixedEmbedder([1.0, 0.0]),
        confirmer=_FixedConfirmer(DedupVerdict.duplicate),
    )
    await db_session.commit()
    assert outcomes[0].action is DedupAction.merged
    assert outcomes[0].hypothesis_id == existing.id

    rows = (
        (await db_session.execute(select(Hypothesis))).scalars().all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_persist_hypotheses_supersedes_existing(
    db_session: AsyncSession,
) -> None:
    from app.services.strategies.funnel_research._hypotheses import persist_hypotheses

    run_id = await _make_run(db_session)
    old = Hypothesis(
        claim_text="old framing",
        scope_entity_ids=[],
        scope_theme_ids=[],
        status=HypothesisStatus.active.value,
        embedding=[1.0, 0.0],
    )
    db_session.add(old)
    await db_session.flush()
    await db_session.commit()

    proposed = [
        ProposedHypothesis(
            claim_text="newer sharper framing",
            scope_entity_ids=[],
            evidence_ids=[],
        )
    ]
    outcomes = await persist_hypotheses(
        session=db_session,
        run_id=run_id,
        proposed=proposed,
        embedder=_FixedEmbedder([1.0, 0.0]),
        confirmer=_FixedConfirmer(DedupVerdict.supersedes),
    )
    await db_session.commit()
    assert outcomes[0].action is DedupAction.superseded
    assert outcomes[0].predecessor_id == old.id

    rows = (
        (await db_session.execute(select(Hypothesis))).scalars().all()
    )
    assert len(rows) == 2

    refreshed_old = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == old.id)
        )
    ).scalar_one()
    assert refreshed_old.status == HypothesisStatus.superseded.value


@pytest.mark.asyncio
async def test_persist_hypotheses_only_mirrors_newly_inserted_rows(
    db_session: AsyncSession,
) -> None:
    """When dedup merges into an existing row, no fresh mirror entity is
    created — the existing hypothesis already has its own mirror."""
    from app.services.strategies.funnel_research._hypotheses import persist_hypotheses

    run_id = await _make_run(db_session)
    existing = Hypothesis(
        claim_text="energy outperforms",
        scope_entity_ids=[],
        scope_theme_ids=[],
        status=HypothesisStatus.active.value,
        embedding=[1.0, 0.0],
    )
    db_session.add(existing)
    await db_session.flush()
    await db_session.commit()

    initial_entity_count = (
        await db_session.execute(select(Entity).where(Entity.type == "hypothesis"))
    ).scalars().all()
    initial_count = len(initial_entity_count)

    proposed = [
        ProposedHypothesis(
            claim_text="energy outperforms (duplicate)",
            scope_entity_ids=[],
            evidence_ids=[],
        )
    ]
    outcomes = await persist_hypotheses(
        session=db_session,
        run_id=run_id,
        proposed=proposed,
        embedder=_FixedEmbedder([1.0, 0.0]),
        confirmer=_FixedConfirmer(DedupVerdict.duplicate),
    )
    await db_session.commit()
    assert outcomes[0].action is DedupAction.merged

    final = (
        (await db_session.execute(select(Entity).where(Entity.type == "hypothesis")))
        .scalars()
        .all()
    )
    assert len(final) == initial_count


@pytest.mark.asyncio
async def test_persist_hypotheses_uses_distinct_embedder_to_avoid_false_merge(
    db_session: AsyncSession,
) -> None:
    """Two genuinely distinct claims should both be inserted when the
    embedder produces meaningfully different vectors."""
    from app.services.strategies.funnel_research._hypotheses import persist_hypotheses

    run_id = await _make_run(db_session)
    proposed = [
        ProposedHypothesis(
            claim_text="oil prices spike on supply cut",
            scope_entity_ids=[],
            evidence_ids=[],
        ),
        ProposedHypothesis(
            claim_text="ai capex slows in 2027",
            scope_entity_ids=[],
            evidence_ids=[],
        ),
    ]
    outcomes = await persist_hypotheses(
        session=db_session,
        run_id=run_id,
        proposed=proposed,
        embedder=_DistinctEmbedder(),
        confirmer=_FixedConfirmer(DedupVerdict.duplicate),
    )
    await db_session.commit()
    assert all(o.action is DedupAction.inserted for o in outcomes)
    assert outcomes[0].hypothesis_id != outcomes[1].hypothesis_id


@pytest.mark.asyncio
async def test_persist_hypotheses_stores_embedding_when_embedder_supplied(
    db_session: AsyncSession,
) -> None:
    """Production wiring depends on the embedding being persisted so the
    next run's dedup pass can compare against it. Regression for the
    wired-in funnel path."""
    from app.services.strategies.funnel_research._hypotheses import persist_hypotheses

    run_id = await _make_run(db_session)
    embedder = _FixedEmbedder([0.6, 0.8])
    proposed = [
        ProposedHypothesis(
            claim_text="rates re-priced into 2027",
            scope_entity_ids=[],
            evidence_ids=[],
        )
    ]
    outcomes = await persist_hypotheses(
        session=db_session,
        run_id=run_id,
        proposed=proposed,
        embedder=embedder,
    )
    await db_session.commit()

    stored = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == outcomes[0].hypothesis_id)
        )
    ).scalar_one()
    assert stored.embedding == [0.6, 0.8]


@pytest.mark.asyncio
async def test_persist_hypotheses_skips_embedding_when_embedder_omitted(
    db_session: AsyncSession,
) -> None:
    from app.services.strategies.funnel_research._hypotheses import persist_hypotheses

    run_id = await _make_run(db_session)
    proposed = [
        ProposedHypothesis(
            claim_text="no embedder available",
            scope_entity_ids=[],
            evidence_ids=[],
        )
    ]
    outcomes = await persist_hypotheses(
        session=db_session, run_id=run_id, proposed=proposed
    )
    await db_session.commit()
    stored = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == outcomes[0].hypothesis_id)
        )
    ).scalar_one()
    assert stored.embedding is None


class _FailingEmbedder:
    """Embedder that raises on every call — simulates a transient embedding outage."""

    async def embed(self, text: str) -> list[float]:
        raise RuntimeError("simulated embedding outage")


@pytest.mark.asyncio
async def test_persist_hypotheses_degrades_to_no_embedding_on_embedder_failure(
    db_session: AsyncSession,
) -> None:
    """A transient embedder failure must not abort the run.

    The hypothesis is still inserted (embedding-less), a warn-level
    `hypothesis_embedding_failure` event is recorded, and dedup is skipped
    because `resolve_duplicate` treats `embedding=None` as "no candidates".
    """
    from app.db.models_runs import RunEvent, RunEventLevel
    from app.services.strategies.funnel_research._hypotheses import persist_hypotheses

    run_id = await _make_run(db_session)
    proposed = [
        ProposedHypothesis(
            claim_text="Energy outperforms",
            scope_entity_ids=[uuid.uuid4()],
            evidence_ids=[uuid.uuid4()],
        )
    ]
    outcomes = await persist_hypotheses(
        session=db_session,
        run_id=run_id,
        proposed=proposed,
        embedder=_FailingEmbedder(),
    )
    await db_session.commit()

    assert len(outcomes) == 1
    assert outcomes[0].action is DedupAction.inserted
    stored = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == outcomes[0].hypothesis_id)
        )
    ).scalar_one()
    assert stored.embedding is None

    warn_events = (
        await db_session.execute(
            select(RunEvent).where(
                RunEvent.run_id == run_id, RunEvent.level == RunEventLevel.warn
            )
        )
    ).scalars().all()
    assert any(
        isinstance(event.data, dict)
        and event.data.get("event") == "hypothesis_embedding_failure"
        for event in warn_events
    )


@pytest.mark.asyncio
async def test_persist_hypotheses_embedder_failure_does_not_block_subsequent_claims(
    db_session: AsyncSession,
) -> None:
    """A failed embedding on claim N should not block claim N+1."""
    from app.services.strategies.funnel_research._hypotheses import persist_hypotheses

    run_id = await _make_run(db_session)
    proposed = [
        ProposedHypothesis(
            claim_text="Energy outperforms",
            scope_entity_ids=[uuid.uuid4()],
            evidence_ids=[uuid.uuid4()],
        ),
        ProposedHypothesis(
            claim_text="Healthcare lags",
            scope_entity_ids=[uuid.uuid4()],
            evidence_ids=[uuid.uuid4()],
        ),
    ]
    outcomes = await persist_hypotheses(
        session=db_session,
        run_id=run_id,
        proposed=proposed,
        embedder=_FailingEmbedder(),
    )
    await db_session.commit()
    assert len(outcomes) == 2
    assert all(outcome.action is DedupAction.inserted for outcome in outcomes)
