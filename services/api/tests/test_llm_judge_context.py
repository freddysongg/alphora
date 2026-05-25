from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_company import CompanyThesis
from app.db.models_graph import (
    Entity,
    Hypothesis,
    HypothesisStatus,
)
from app.db.models_macro import MacroBrief
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.db.models_sector import SectorBrief
from app.services.llm_judge_context import (
    MAX_HYPOTHESES,
    JudgeContext,
    gather_context,
    is_sparse,
)


async def _make_research_run(session: AsyncSession) -> uuid.UUID:
    run_id = uuid.uuid4()
    session.add(
        ResearchRun(
            id=run_id,
            trade_date=date.today(),
            strategy=Strategy.funnel_research.value,
            status=RunStatus.succeeded,
            config={},
        )
    )
    await session.flush()
    return run_id


@pytest.mark.asyncio
async def test_gather_context_returns_empty_when_no_entity_for_ticker(
    db_session: AsyncSession,
) -> None:
    ctx = await gather_context(db_session, ticker="ZZZZ")
    assert isinstance(ctx, JudgeContext)
    assert ctx.entity_id is None
    assert ctx.company_thesis is None
    assert ctx.hypotheses == []
    assert ctx.evidence == []
    assert is_sparse(ctx) is True


@pytest.mark.asyncio
async def test_gather_context_finds_entity_by_ticker_normalized(
    db_session: AsyncSession,
) -> None:
    entity = Entity(
        id=uuid.uuid4(),
        type="company",
        canonical_name="Nvidia Corp",
        aliases=["NVDA"],
        external_ids={},
        attributes={},
        ticker_normalized="NVDA",
        confidence=1.0,
    )
    db_session.add(entity)
    await db_session.commit()

    ctx = await gather_context(db_session, ticker="NVDA")
    assert ctx.entity_id == entity.id


@pytest.mark.asyncio
async def test_gather_context_collects_active_hypotheses_for_entity(
    db_session: AsyncSession,
) -> None:
    entity = Entity(
        id=uuid.uuid4(),
        type="company",
        canonical_name="Nvidia Corp",
        aliases=[],
        external_ids={},
        attributes={},
        ticker_normalized="NVDA",
        confidence=1.0,
    )
    db_session.add(entity)
    hypo_high = Hypothesis(
        id=uuid.uuid4(),
        claim_text="data-center growth re-accelerates Q3",
        scope_entity_ids=[str(entity.id)],
        scope_theme_ids=[],
        status=HypothesisStatus.active.value,
        belief=0.85,
        last_activity_at=datetime.now(UTC) - timedelta(hours=12),
    )
    hypo_low = Hypothesis(
        id=uuid.uuid4(),
        claim_text="export controls expand to mid-tier accelerators",
        scope_entity_ids=[str(entity.id)],
        scope_theme_ids=[],
        status=HypothesisStatus.active.value,
        belief=0.32,
        last_activity_at=datetime.now(UTC) - timedelta(hours=2),
    )
    hypo_stale = Hypothesis(
        id=uuid.uuid4(),
        claim_text="old crypto-mining thesis from 2021",
        scope_entity_ids=[str(entity.id)],
        scope_theme_ids=[],
        status=HypothesisStatus.active.value,
        belief=0.4,
        last_activity_at=datetime.now(UTC) - timedelta(days=180),
    )
    hypo_falsified = Hypothesis(
        id=uuid.uuid4(),
        claim_text="competitor releases comparable chip",
        scope_entity_ids=[str(entity.id)],
        scope_theme_ids=[],
        status=HypothesisStatus.falsified.value,
        belief=0.1,
        last_activity_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add_all([hypo_high, hypo_low, hypo_stale, hypo_falsified])
    await db_session.commit()

    ctx = await gather_context(db_session, ticker="NVDA")
    assert ctx.entity_id == entity.id
    returned_ids = {h["id"] for h in ctx.hypotheses}
    assert hypo_high.id.hex in returned_ids or str(hypo_high.id) in returned_ids
    assert hypo_low.id.hex in returned_ids or str(hypo_low.id) in returned_ids
    assert hypo_stale.id.hex not in returned_ids and str(hypo_stale.id) not in returned_ids
    assert hypo_falsified.id.hex not in returned_ids and str(hypo_falsified.id) not in returned_ids
    assert ctx.hypotheses[0]["belief"] >= ctx.hypotheses[-1]["belief"]
    assert is_sparse(ctx) is False


@pytest.mark.asyncio
async def test_gather_context_caps_hypotheses_at_max(
    db_session: AsyncSession,
) -> None:
    entity = Entity(
        id=uuid.uuid4(),
        type="company",
        canonical_name="ACME",
        aliases=[],
        external_ids={},
        attributes={},
        ticker_normalized="ACME",
        confidence=1.0,
    )
    db_session.add(entity)
    for i in range(MAX_HYPOTHESES + 5):
        db_session.add(
            Hypothesis(
                id=uuid.uuid4(),
                claim_text=f"claim {i}",
                scope_entity_ids=[str(entity.id)],
                scope_theme_ids=[],
                status=HypothesisStatus.active.value,
                belief=0.5 + i * 0.01,
                last_activity_at=datetime.now(UTC) - timedelta(hours=i),
            )
        )
    await db_session.commit()
    ctx = await gather_context(db_session, ticker="ACME")
    assert len(ctx.hypotheses) == MAX_HYPOTHESES


@pytest.mark.asyncio
async def test_gather_context_truncates_long_claim_text(
    db_session: AsyncSession,
) -> None:
    entity = Entity(
        id=uuid.uuid4(),
        type="company",
        canonical_name="ACME",
        aliases=[],
        external_ids={},
        attributes={},
        ticker_normalized="ACME",
        confidence=1.0,
    )
    db_session.add(entity)
    db_session.add(
        Hypothesis(
            id=uuid.uuid4(),
            claim_text="a" * 1000,
            scope_entity_ids=[str(entity.id)],
            scope_theme_ids=[],
            status=HypothesisStatus.active.value,
            belief=0.5,
            last_activity_at=datetime.now(UTC),
        )
    )
    await db_session.commit()
    ctx = await gather_context(db_session, ticker="ACME")
    claim = ctx.hypotheses[0]["claim_text"]
    assert isinstance(claim, str)
    assert len(claim) <= 281
    assert claim.endswith("…")


@pytest.mark.asyncio
async def test_gather_context_pulls_company_thesis_and_macro_and_sector(
    db_session: AsyncSession,
) -> None:
    research_run_id = await _make_research_run(db_session)
    sector_entity = Entity(
        id=uuid.uuid4(),
        type="sector",
        canonical_name="Semiconductors",
        aliases=[],
        external_ids={},
        attributes={},
        ticker_normalized=None,
        confidence=1.0,
    )
    company_entity = Entity(
        id=uuid.uuid4(),
        type="company",
        canonical_name="Nvidia Corp",
        aliases=[],
        external_ids={},
        attributes={"sector_entity_id": None},
        ticker_normalized="NVDA",
        confidence=1.0,
    )
    db_session.add_all([sector_entity, company_entity])
    await db_session.flush()
    db_session.add(
        CompanyThesis(
            id=uuid.uuid4(),
            run_id=research_run_id,
            company_entity_id=company_entity.id,
            sector_entity_id=sector_entity.id,
            ticker="NVDA",
            direction="overweight",
            payload={"summary": "structural compute demand"},
            verifier_status="verified",
            wall_clock_ms=1000,
        )
    )
    db_session.add(
        SectorBrief(
            id=uuid.uuid4(),
            run_id=research_run_id,
            sector_entity_id=sector_entity.id,
            direction="overweight",
            payload={"summary": "AI capex sustains"},
            verifier_status="verified",
            wall_clock_ms=500,
        )
    )
    db_session.add(
        MacroBrief(
            id=uuid.uuid4(),
            run_id=research_run_id,
            themes=[{"label": "FOMC dovish hold"}],
            sector_calls=[{"sector": "Semiconductors", "direction": "overweight"}],
            watch_items=[],
            cited_claims=[],
            proposed_hypotheses=[],
            confidence=0.7,
            verifier_status="verified",
            evidence_ids=[],
        )
    )
    await db_session.commit()

    ctx = await gather_context(db_session, ticker="NVDA")
    assert ctx.company_thesis is not None
    assert ctx.company_thesis["direction"] == "overweight"
    assert ctx.sector_brief is not None
    assert ctx.sector_brief["direction"] == "overweight"
    assert ctx.macro_brief is not None
    assert ctx.macro_brief["themes"][0]["label"] == "FOMC dovish hold"
    assert is_sparse(ctx) is False


@pytest.mark.asyncio
async def test_is_sparse_true_when_only_macro_brief_present(
    db_session: AsyncSession,
) -> None:
    """Macro alone is not enough to judge a ticker-specific trade."""
    research_run_id = await _make_research_run(db_session)
    db_session.add(
        MacroBrief(
            id=uuid.uuid4(),
            run_id=research_run_id,
            themes=[{"label": "rates stable"}],
            sector_calls=[],
            watch_items=[],
            cited_claims=[],
            proposed_hypotheses=[],
            confidence=0.7,
            verifier_status="verified",
            evidence_ids=[],
        )
    )
    await db_session.commit()
    ctx = await gather_context(db_session, ticker="ZZZZ")
    assert ctx.macro_brief is not None
    assert is_sparse(ctx) is True
