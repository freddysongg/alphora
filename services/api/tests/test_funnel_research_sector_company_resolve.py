"""Tests for the sector-time company entity-id resolver.

This helper runs at sector brief persistence time so the persisted brief
carries a `company_entity_id` per company idea — enabling the web UI to
link company names to the company thesis page without re-resolving on read.
"""
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType
from app.schemas.macro_brief import SectorCallDirection, VerifierStatus
from app.schemas.sector_brief import SectorBrief, SectorCompanyIdea
from app.services.strategies.funnel_research.sector.resolve import (
    resolve_sector_company_entity_ids,
)


def _brief_with_companies(
    sector_id: uuid.UUID, companies: list[SectorCompanyIdea]
) -> SectorBrief:
    return SectorBrief(
        sector_entity_id=sector_id,
        sector_name="Information Technology",
        direction=SectorCallDirection.overweight,
        themes=[],
        companies=companies,
        watch_items=[],
        cited_claims=[],
        confidence=0.7,
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


@pytest.mark.asyncio
async def test_resolve_sector_company_entity_ids_populates_from_ticker(
    db_session: AsyncSession,
) -> None:
    sector_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    db_session.add(
        Entity(
            id=company_entity_id,
            type=EntityType.company.value,
            canonical_name="Apple Inc.",
            aliases=[],
            external_ids={"ticker": "AAPL"},
            ticker_normalized="AAPL",
        )
    )
    await db_session.commit()

    brief = _brief_with_companies(
        sector_id,
        [
            SectorCompanyIdea(
                name="Apple",
                ticker="AAPL",
                direction=SectorCallDirection.overweight,
                conviction=0.8,
                evidence_ids=[],
            )
        ],
    )

    resolved = await resolve_sector_company_entity_ids(
        session=db_session, brief=brief
    )

    assert len(resolved.companies) == 1
    assert resolved.companies[0].company_entity_id == company_entity_id


@pytest.mark.asyncio
async def test_resolve_sector_company_entity_ids_leaves_none_when_no_match(
    db_session: AsyncSession,
) -> None:
    sector_id = uuid.uuid4()
    brief = _brief_with_companies(
        sector_id,
        [
            SectorCompanyIdea(
                name="Unknown Co",
                ticker="UNKN",
                direction=SectorCallDirection.overweight,
                conviction=0.5,
                evidence_ids=[],
            )
        ],
    )

    resolved = await resolve_sector_company_entity_ids(
        session=db_session, brief=brief
    )

    assert resolved.companies[0].company_entity_id is None


@pytest.mark.asyncio
async def test_resolve_sector_company_entity_ids_preserves_other_fields(
    db_session: AsyncSession,
) -> None:
    sector_id = uuid.uuid4()
    evidence_id = uuid.uuid4()
    brief = _brief_with_companies(
        sector_id,
        [
            SectorCompanyIdea(
                name="Apple",
                ticker="AAPL",
                direction=SectorCallDirection.overweight,
                conviction=0.8,
                evidence_ids=[evidence_id],
            )
        ],
    )

    resolved = await resolve_sector_company_entity_ids(
        session=db_session, brief=brief
    )

    company = resolved.companies[0]
    assert company.name == "Apple"
    assert company.ticker == "AAPL"
    assert company.direction is SectorCallDirection.overweight
    assert company.conviction == 0.8
    assert company.evidence_ids == [evidence_id]
    assert resolved.sector_entity_id == sector_id
    assert resolved.sector_name == "Information Technology"


@pytest.mark.asyncio
async def test_resolve_sector_company_entity_ids_falls_back_to_alias(
    db_session: AsyncSession,
) -> None:
    sector_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    db_session.add(
        Entity(
            id=company_entity_id,
            type=EntityType.company.value,
            canonical_name="Alphabet Inc.",
            aliases=["Google"],
            external_ids={},
            ticker_normalized=None,
        )
    )
    await db_session.commit()

    brief = _brief_with_companies(
        sector_id,
        [
            SectorCompanyIdea(
                name="Google",
                ticker=None,
                direction=SectorCallDirection.overweight,
                conviction=0.6,
                evidence_ids=[],
            )
        ],
    )

    resolved = await resolve_sector_company_entity_ids(
        session=db_session, brief=brief
    )

    assert resolved.companies[0].company_entity_id == company_entity_id
