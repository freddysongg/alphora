import uuid

import pytest
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
