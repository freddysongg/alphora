import uuid

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType
from app.schemas.macro_brief import SectorCallDirection, VerifierStatus
from app.schemas.sector_brief import (
    JudgePublic,
    JudgeStatus,
    SectorBrief,
    SectorBriefPublic,
    SectorCompanyIdea,
)
from app.services.strategies.funnel_research.company import (
    company_resolution_key,
    select_companies,
)
from app.services.strategies.funnel_research.core import _build_company_resolutions


def _sector_brief_public(
    *,
    sector_entity_id: uuid.UUID,
    sector_name: str,
    companies: list[SectorCompanyIdea],
) -> SectorBriefPublic:
    return SectorBriefPublic(
        brief=SectorBrief(
            sector_entity_id=sector_entity_id,
            sector_name=sector_name,
            direction=SectorCallDirection.overweight,
            themes=[],
            companies=companies,
            watch_items=[],
            cited_claims=[],
            confidence=0.7,
            verifier_status=VerifierStatus.verified,
            regeneration_count=0,
        ),
        judge=JudgePublic(status=JudgeStatus.not_run, reasons=[], call_id=None),
        chunks=[],
    )


@pytest.mark.asyncio
async def test_build_company_resolutions_reads_cik_from_sec_bootstrap_key(
    db_session: AsyncSession,
) -> None:
    """`bootstrap_from_sec_cik` writes external_ids["cik"]; the resolver
    must read the same key, not "sec_cik"."""
    sector_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    db_session.add(
        Entity(
            id=company_entity_id,
            type=EntityType.company.value,
            canonical_name="Apple Inc.",
            aliases=["apple"],
            external_ids={"cik": "0000320193", "ticker": "AAPL"},
            ticker_normalized="AAPL",
        )
    )
    await db_session.commit()

    sector_briefs = [
        _sector_brief_public(
            sector_entity_id=sector_id,
            sector_name="Information Technology",
            companies=[
                SectorCompanyIdea(
                    name="Apple Inc.",
                    ticker="AAPL",
                    direction=SectorCallDirection.overweight,
                    conviction=0.8,
                    evidence_ids=[],
                )
            ],
        )
    ]
    selected = select_companies(sector_briefs)
    assert len(selected) == 1
    key = company_resolution_key(selected[0])

    resolutions = await _build_company_resolutions(
        session=db_session, sector_briefs=sector_briefs
    )

    assert key in resolutions
    resolution = resolutions[key]
    assert resolution.company_entity_id == company_entity_id
    assert resolution.cik == "0000320193"


@pytest.mark.asyncio
async def test_build_company_resolutions_matches_by_ticker_when_canonical_name_differs(
    db_session: AsyncSession,
) -> None:
    """An idea name="Apple" with ticker="AAPL" must resolve to the entity
    whose external_ids["ticker"]="AAPL" even when canonical_name is "Apple Inc."""
    sector_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    db_session.add(
        Entity(
            id=company_entity_id,
            type=EntityType.company.value,
            canonical_name="Apple Inc.",
            aliases=[],
            external_ids={"cik": "0000320193", "ticker": "AAPL"},
            ticker_normalized="AAPL",
        )
    )
    await db_session.commit()

    sector_briefs = [
        _sector_brief_public(
            sector_entity_id=sector_id,
            sector_name="Information Technology",
            companies=[
                SectorCompanyIdea(
                    name="Apple",
                    ticker="AAPL",
                    direction=SectorCallDirection.overweight,
                    conviction=0.8,
                    evidence_ids=[],
                )
            ],
        )
    ]
    key = company_resolution_key(select_companies(sector_briefs)[0])

    resolutions = await _build_company_resolutions(
        session=db_session, sector_briefs=sector_briefs
    )

    assert key in resolutions
    assert resolutions[key].company_entity_id == company_entity_id
    assert resolutions[key].cik == "0000320193"


@pytest.mark.asyncio
async def test_build_company_resolutions_prefers_ticker_over_canonical_name(
    db_session: AsyncSession,
) -> None:
    """When ticker matches one entity and canonical_name matches another,
    ticker wins (since company_resolution_key prefers ticker)."""
    sector_id = uuid.uuid4()
    ticker_entity_id = uuid.uuid4()
    name_entity_id = uuid.uuid4()
    db_session.add_all(
        [
            Entity(
                id=ticker_entity_id,
                type=EntityType.company.value,
                canonical_name="Microsoft Corporation",
                aliases=[],
                external_ids={"ticker": "MSFT"},
                ticker_normalized="MSFT",
            ),
            Entity(
                id=name_entity_id,
                type=EntityType.company.value,
                canonical_name="Microsoft",
                aliases=[],
                external_ids={"ticker": "OTHER"},
                ticker_normalized="OTHER",
            ),
        ]
    )
    await db_session.commit()

    sector_briefs = [
        _sector_brief_public(
            sector_entity_id=sector_id,
            sector_name="Information Technology",
            companies=[
                SectorCompanyIdea(
                    name="Microsoft",
                    ticker="MSFT",
                    direction=SectorCallDirection.overweight,
                    conviction=0.8,
                    evidence_ids=[],
                )
            ],
        )
    ]
    key = company_resolution_key(select_companies(sector_briefs)[0])

    resolutions = await _build_company_resolutions(
        session=db_session, sector_briefs=sector_briefs
    )

    assert resolutions[key].company_entity_id == ticker_entity_id


@pytest.mark.asyncio
async def test_build_company_resolutions_matches_by_alias_when_no_ticker_or_canonical_match(
    db_session: AsyncSession,
) -> None:
    """When the idea has no ticker and the canonical_name does not match,
    fall through to alias matching."""
    sector_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    db_session.add(
        Entity(
            id=company_entity_id,
            type=EntityType.company.value,
            canonical_name="Alphabet Inc.",
            aliases=["Google"],
            external_ids={"cik": "0001652044"},
        )
    )
    await db_session.commit()

    sector_briefs = [
        _sector_brief_public(
            sector_entity_id=sector_id,
            sector_name="Communication Services",
            companies=[
                SectorCompanyIdea(
                    name="Google",
                    ticker=None,
                    direction=SectorCallDirection.overweight,
                    conviction=0.7,
                    evidence_ids=[],
                )
            ],
        )
    ]
    key = company_resolution_key(select_companies(sector_briefs)[0])

    resolutions = await _build_company_resolutions(
        session=db_session, sector_briefs=sector_briefs
    )

    assert key in resolutions
    assert resolutions[key].company_entity_id == company_entity_id
    assert resolutions[key].cik == "0001652044"


@pytest.mark.asyncio
async def test_build_company_resolutions_returns_none_cik_when_missing(
    db_session: AsyncSession,
) -> None:
    sector_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    db_session.add(
        Entity(
            id=company_entity_id,
            type=EntityType.company.value,
            canonical_name="Privately Held Co",
            aliases=[],
            external_ids={"ticker": "PRIV"},
            ticker_normalized="PRIV",
        )
    )
    await db_session.commit()

    sector_briefs = [
        _sector_brief_public(
            sector_entity_id=sector_id,
            sector_name="Industrials",
            companies=[
                SectorCompanyIdea(
                    name="Privately Held Co",
                    ticker="PRIV",
                    direction=SectorCallDirection.overweight,
                    conviction=0.6,
                    evidence_ids=[],
                )
            ],
        )
    ]
    key = company_resolution_key(select_companies(sector_briefs)[0])

    resolutions = await _build_company_resolutions(
        session=db_session, sector_briefs=sector_briefs
    )

    assert resolutions[key].cik is None


@pytest.mark.asyncio
async def test_build_company_resolutions_uses_narrow_query_when_idea_matches_by_ticker(
    db_session: AsyncSession,
) -> None:
    """When every selected idea matches by canonical_name or ticker, the resolver
    issues a single narrow SELECT — not a full table scan that loads every
    company entity for an in-Python alias scan."""
    from app.db.session import engine

    sector_id = uuid.uuid4()
    matching_id = uuid.uuid4()
    db_session.add_all(
        [
            Entity(
                id=matching_id,
                type=EntityType.company.value,
                canonical_name="Apple Inc.",
                aliases=[],
                external_ids={"cik": "0000320193", "ticker": "AAPL"},
                ticker_normalized="AAPL",
            ),
            Entity(
                id=uuid.uuid4(),
                type=EntityType.company.value,
                canonical_name="Unrelated Co",
                aliases=[],
                external_ids={"ticker": "ZZZZ"},
                ticker_normalized="ZZZZ",
            ),
        ]
    )
    await db_session.commit()

    sector_briefs = [
        _sector_brief_public(
            sector_entity_id=sector_id,
            sector_name="Information Technology",
            companies=[
                SectorCompanyIdea(
                    name="Apple",
                    ticker="AAPL",
                    direction=SectorCallDirection.overweight,
                    conviction=0.8,
                    evidence_ids=[],
                )
            ],
        )
    ]

    entity_select_count = 0
    last_entity_select: str = ""

    def _on_cursor_execute(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        nonlocal entity_select_count, last_entity_select
        normalized = statement.upper().replace('"', "").replace("`", "")
        if "FROM ENTITIES" in normalized and "INSERT" not in normalized:
            entity_select_count += 1
            last_entity_select = normalized

    event.listen(engine.sync_engine, "before_cursor_execute", _on_cursor_execute)
    try:
        resolutions = await _build_company_resolutions(
            session=db_session, sector_briefs=sector_briefs
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _on_cursor_execute)

    key = company_resolution_key(select_companies(sector_briefs)[0])
    assert resolutions[key].company_entity_id == matching_id
    assert entity_select_count == 1, (
        f"expected single narrow SELECT, got {entity_select_count}"
    )
    assert "TICKER_NORMALIZED" in last_entity_select, (
        f"narrow query should reference ticker_normalized; got: {last_entity_select}"
    )


@pytest.mark.asyncio
async def test_build_company_resolutions_falls_back_to_alias_load_when_narrow_query_misses(
    db_session: AsyncSession,
) -> None:
    """When an idea matches only by alias, the narrow query misses, so a second
    broader load runs to scan aliases in Python — exactly two SELECTs total."""
    from app.db.session import engine

    sector_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    db_session.add(
        Entity(
            id=company_entity_id,
            type=EntityType.company.value,
            canonical_name="Alphabet Inc.",
            aliases=["Google"],
            external_ids={"cik": "0001652044"},
            ticker_normalized=None,
        )
    )
    await db_session.commit()

    sector_briefs = [
        _sector_brief_public(
            sector_entity_id=sector_id,
            sector_name="Communication Services",
            companies=[
                SectorCompanyIdea(
                    name="Google",
                    ticker=None,
                    direction=SectorCallDirection.overweight,
                    conviction=0.7,
                    evidence_ids=[],
                )
            ],
        )
    ]

    entity_select_count = 0

    def _on_cursor_execute(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        nonlocal entity_select_count
        normalized = statement.upper().replace('"', "").replace("`", "")
        if "FROM ENTITIES" in normalized and "INSERT" not in normalized:
            entity_select_count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", _on_cursor_execute)
    try:
        resolutions = await _build_company_resolutions(
            session=db_session, sector_briefs=sector_briefs
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _on_cursor_execute)

    key = company_resolution_key(select_companies(sector_briefs)[0])
    assert resolutions[key].company_entity_id == company_entity_id
    assert entity_select_count == 2, (
        f"expected narrow + alias fallback (2 SELECTs), got {entity_select_count}"
    )
