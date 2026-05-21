import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType, Hypothesis
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.db.models_sector import SectorBrief as SectorBriefRow
from app.services.strategies.funnel_research._themes import (
    normalize_theme_slug,
    promote_themes,
)


def test_normalize_theme_slug_lowercases_strips_and_ascii_folds() -> None:
    assert normalize_theme_slug("AI Capex") == "ai capex"
    assert normalize_theme_slug("  Energy   Independence  ") == "energy independence"
    assert normalize_theme_slug("Résumé Inflation") == "resume inflation"
    assert normalize_theme_slug("") == ""


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 19),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.flush()
    return run.id


async def _seed_sector_entity(session: AsyncSession, name: str) -> uuid.UUID:
    entity = Entity(
        type=EntityType.sector.value,
        canonical_name=name,
        attributes={"gics_code": "10", "gics_level": 1, "parent_gics_code": None},
    )
    session.add(entity)
    await session.flush()
    return entity.id


def _theme_dict(name: str) -> dict[str, object]:
    return {"name": name, "evidence_ids": [], "confidence": 0.5}


def _sector_payload(
    *, sector_entity_id: uuid.UUID, sector_name: str, theme_names: list[str]
) -> dict[str, object]:
    return {
        "sector_entity_id": str(sector_entity_id),
        "sector_name": sector_name,
        "direction": "overweight",
        "themes": [_theme_dict(name) for name in theme_names],
        "companies": [],
        "watch_items": [],
        "cited_claims": [],
        "confidence": 0.7,
        "verifier_status": "verified",
        "regeneration_count": 0,
    }


@pytest.mark.asyncio
async def test_promote_themes_returns_empty_when_only_one_brief(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    macro = MacroBriefRow(
        run_id=run_id,
        themes=[_theme_dict("AI Capex")],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.5,
        verifier_status="verified",
        regeneration_count=0,
        evidence_ids=[],
        judge_status="passed",
    )
    db_session.add(macro)
    await db_session.commit()

    promoted = await promote_themes(session=db_session, run_id=run_id)
    assert promoted == []
    theme_count = (
        await db_session.execute(
            select(Entity).where(Entity.type == EntityType.theme.value)
        )
    ).scalars().all()
    assert len(theme_count) == 0


@pytest.mark.asyncio
async def test_promote_themes_promotes_slug_seen_in_two_briefs(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_entity_id = await _seed_sector_entity(db_session, "Energy")

    macro = MacroBriefRow(
        run_id=run_id,
        themes=[_theme_dict("Onshoring"), _theme_dict("AI Capex")],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.5,
        verifier_status="verified",
        regeneration_count=0,
        evidence_ids=[],
        judge_status="passed",
    )
    db_session.add(macro)

    sector_row = SectorBriefRow(
        run_id=run_id,
        sector_entity_id=sector_entity_id,
        direction="overweight",
        payload=_sector_payload(
            sector_entity_id=sector_entity_id,
            sector_name="Energy",
            theme_names=["AI Capex"],
        ),
        verifier_status="verified",
        regeneration_count=0,
        judge_status="passed",
        judge_reasons=None,
        judge_call_id=None,
        wall_clock_ms=100,
    )
    db_session.add(sector_row)
    await db_session.commit()

    promoted = await promote_themes(session=db_session, run_id=run_id)
    assert len(promoted) == 1

    themes = (
        (
            await db_session.execute(
                select(Entity).where(Entity.type == EntityType.theme.value)
            )
        )
        .scalars()
        .all()
    )
    assert len(themes) == 1
    assert themes[0].canonical_name == "AI Capex"
    assert (themes[0].attributes or {}).get("normalized_slug") == "ai capex"


@pytest.mark.asyncio
async def test_promote_themes_treats_not_run_judge_as_passing(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_entity_id = await _seed_sector_entity(db_session, "Energy")

    macro = MacroBriefRow(
        run_id=run_id,
        themes=[_theme_dict("AI Capex")],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.5,
        verifier_status="verified",
        regeneration_count=0,
        evidence_ids=[],
        judge_status="not_run",
    )
    db_session.add(macro)

    sector_row = SectorBriefRow(
        run_id=run_id,
        sector_entity_id=sector_entity_id,
        direction="overweight",
        payload=_sector_payload(
            sector_entity_id=sector_entity_id,
            sector_name="Energy",
            theme_names=["AI Capex"],
        ),
        verifier_status="verified",
        regeneration_count=0,
        judge_status="not_run",
        judge_reasons=None,
        judge_call_id=None,
        wall_clock_ms=100,
    )
    db_session.add(sector_row)
    await db_session.commit()

    promoted = await promote_themes(session=db_session, run_id=run_id)
    assert len(promoted) == 1


@pytest.mark.asyncio
async def test_promote_themes_skips_flagged_briefs(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_entity_id = await _seed_sector_entity(db_session, "Energy")

    macro = MacroBriefRow(
        run_id=run_id,
        themes=[_theme_dict("AI Capex")],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.5,
        verifier_status="verified",
        regeneration_count=0,
        evidence_ids=[],
        judge_status="flagged",
    )
    db_session.add(macro)

    sector_row = SectorBriefRow(
        run_id=run_id,
        sector_entity_id=sector_entity_id,
        direction="overweight",
        payload=_sector_payload(
            sector_entity_id=sector_entity_id,
            sector_name="Energy",
            theme_names=["AI Capex"],
        ),
        verifier_status="verified",
        regeneration_count=0,
        judge_status="passed",
        judge_reasons=None,
        judge_call_id=None,
        wall_clock_ms=100,
    )
    db_session.add(sector_row)
    await db_session.commit()

    promoted = await promote_themes(session=db_session, run_id=run_id)
    assert promoted == []


@pytest.mark.asyncio
async def test_promote_themes_backfills_hypothesis_scope_theme_ids(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_entity_id = await _seed_sector_entity(db_session, "Energy")

    macro = MacroBriefRow(
        run_id=run_id,
        themes=[_theme_dict("AI Capex")],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.5,
        verifier_status="verified",
        regeneration_count=0,
        evidence_ids=[],
        judge_status="passed",
    )
    db_session.add(macro)

    sector_row = SectorBriefRow(
        run_id=run_id,
        sector_entity_id=sector_entity_id,
        direction="overweight",
        payload=_sector_payload(
            sector_entity_id=sector_entity_id,
            sector_name="Energy",
            theme_names=["AI Capex"],
        ),
        verifier_status="verified",
        regeneration_count=0,
        judge_status="passed",
        judge_reasons=None,
        judge_call_id=None,
        wall_clock_ms=100,
    )
    db_session.add(sector_row)

    matching = Hypothesis(
        claim_text="Capex on AI capex continues to outpace consensus",
        scope_entity_ids=[],
        scope_theme_ids=[],
        proposed_by_run_id=run_id,
    )
    unrelated = Hypothesis(
        claim_text="Energy demand softens in autumn",
        scope_entity_ids=[],
        scope_theme_ids=[],
        proposed_by_run_id=run_id,
    )
    db_session.add_all([matching, unrelated])
    await db_session.commit()

    promoted = await promote_themes(session=db_session, run_id=run_id)
    await db_session.commit()
    assert len(promoted) == 1
    theme_id = promoted[0]

    db_session.expire_all()
    rows = (
        (await db_session.execute(select(Hypothesis).order_by(Hypothesis.claim_text)))
        .scalars()
        .all()
    )
    backfilled = {h.claim_text: list(h.scope_theme_ids or []) for h in rows}
    assert backfilled["Capex on AI capex continues to outpace consensus"] == [
        str(theme_id)
    ]
    assert backfilled["Energy demand softens in autumn"] == []


@pytest.mark.asyncio
async def test_promote_themes_reuses_existing_theme_entity(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    sector_entity_id = await _seed_sector_entity(db_session, "Energy")
    pre_existing = Entity(
        type=EntityType.theme.value,
        canonical_name="AI Capex",
        attributes={"normalized_slug": "ai capex"},
    )
    db_session.add(pre_existing)
    await db_session.flush()

    macro = MacroBriefRow(
        run_id=run_id,
        themes=[_theme_dict("AI Capex")],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.5,
        verifier_status="verified",
        regeneration_count=0,
        evidence_ids=[],
        judge_status="passed",
    )
    db_session.add(macro)

    sector_row = SectorBriefRow(
        run_id=run_id,
        sector_entity_id=sector_entity_id,
        direction="overweight",
        payload=_sector_payload(
            sector_entity_id=sector_entity_id,
            sector_name="Energy",
            theme_names=["AI Capex"],
        ),
        verifier_status="verified",
        regeneration_count=0,
        judge_status="passed",
        judge_reasons=None,
        judge_call_id=None,
        wall_clock_ms=100,
    )
    db_session.add(sector_row)
    await db_session.commit()

    promoted = await promote_themes(session=db_session, run_id=run_id)
    assert promoted == [pre_existing.id]
    themes = (
        (
            await db_session.execute(
                select(Entity).where(Entity.type == EntityType.theme.value)
            )
        )
        .scalars()
        .all()
    )
    assert len(themes) == 1
