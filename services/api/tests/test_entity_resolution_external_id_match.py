from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType


@pytest_asyncio.fixture()
async def populated_session(initialized_schema: None) -> AsyncIterator[AsyncSession]:
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def _seed_entity(
    session: AsyncSession,
    *,
    canonical_name: str,
    external_ids: dict[str, str],
    aliases: list[str] | None = None,
    entity_type: EntityType = EntityType.company,
) -> Entity:
    entity = Entity(
        type=entity_type.value,
        canonical_name=canonical_name,
        aliases=aliases or [],
        external_ids=external_ids,
        attributes={},
        confidence=1.0,
        needs_review=False,
    )
    session.add(entity)
    await session.flush()
    return entity


@pytest.mark.asyncio
async def test_external_id_match_finds_ticker_with_nasdaq_context(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._external_id_match import (
        step_2_external_id_match,
    )

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            external_ids={"ticker": "AAPL", "cik": "0000320193"},
        )

    match = await step_2_external_id_match(
        session=populated_session,
        context_excerpt="Apple Inc. (Nasdaq: AAPL) reported earnings...",
    )

    assert match is not None
    assert match.canonical_name == "Apple Inc."


@pytest.mark.asyncio
async def test_external_id_match_finds_ticker_with_dollar_sign(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._external_id_match import (
        step_2_external_id_match,
    )

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Tesla Inc.",
            external_ids={"ticker": "TSLA"},
        )

    match = await step_2_external_id_match(
        session=populated_session,
        context_excerpt="Heavy trading volume on $TSLA today.",
    )

    assert match is not None
    assert match.canonical_name == "Tesla Inc."


@pytest.mark.asyncio
async def test_external_id_match_finds_ticker_with_nyse_context(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._external_id_match import (
        step_2_external_id_match,
    )

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="JPMorgan Chase & Co.",
            external_ids={"ticker": "JPM"},
        )

    match = await step_2_external_id_match(
        session=populated_session,
        context_excerpt="JPMorgan Chase (NYSE: JPM) announced a buyback.",
    )

    assert match is not None
    assert match.canonical_name == "JPMorgan Chase & Co."


@pytest.mark.asyncio
async def test_external_id_match_finds_cik(populated_session: AsyncSession) -> None:
    from app.services.entity_resolution._external_id_match import (
        step_2_external_id_match,
    )

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            external_ids={"cik": "0000320193"},
        )

    match = await step_2_external_id_match(
        session=populated_session,
        context_excerpt="See filing CIK 0000320193 for details.",
    )

    assert match is not None
    assert match.canonical_name == "Apple Inc."


@pytest.mark.asyncio
async def test_external_id_match_finds_cik_with_short_digits(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._external_id_match import (
        step_2_external_id_match,
    )

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            external_ids={"cik": "0000320193"},
        )

    match = await step_2_external_id_match(
        session=populated_session,
        context_excerpt="See CIK 320193 in the registry.",
    )

    assert match is not None


@pytest.mark.asyncio
async def test_external_id_match_finds_lei(populated_session: AsyncSession) -> None:
    from app.services.entity_resolution._external_id_match import (
        step_2_external_id_match,
    )

    lei = "HWUPKR0MPOU8FGXBT394"
    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            external_ids={"lei": lei},
        )

    match = await step_2_external_id_match(
        session=populated_session,
        context_excerpt=f"Counterparty LEI {lei} is registered.",
    )

    assert match is not None


@pytest.mark.asyncio
async def test_external_id_match_rejects_ticker_without_context_marker(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._external_id_match import (
        step_2_external_id_match,
    )

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            external_ids={"ticker": "AAPL"},
        )

    match = await step_2_external_id_match(
        session=populated_session,
        context_excerpt="The bag is APPLEy in color.",
    )

    assert match is None


@pytest.mark.asyncio
async def test_external_id_match_returns_none_when_ambiguous(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._external_id_match import (
        step_2_external_id_match,
    )

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            external_ids={"ticker": "AAPL"},
        )
        await _seed_entity(
            populated_session,
            canonical_name="Apple Hospitality REIT",
            external_ids={"ticker": "APLE"},
        )

    match = await step_2_external_id_match(
        session=populated_session,
        context_excerpt="Tickers $AAPL and $APLE traded heavily today.",
    )

    assert match is None


@pytest.mark.asyncio
async def test_external_id_match_returns_none_when_no_patterns(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._external_id_match import (
        step_2_external_id_match,
    )

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            external_ids={"ticker": "AAPL"},
        )

    match = await step_2_external_id_match(
        session=populated_session,
        context_excerpt="The earnings report was positive overall.",
    )

    assert match is None


@pytest.mark.asyncio
async def test_external_id_match_skips_merged_tombstones(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._external_id_match import (
        step_2_external_id_match,
    )

    async with populated_session.begin():
        survivor = await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            external_ids={"ticker": "AAPL"},
        )
        tombstone = await _seed_entity(
            populated_session,
            canonical_name="Apple Computer, Inc.",
            external_ids={"ticker": "AAPL"},
        )
        tombstone.merged_into_id = survivor.id

    match = await step_2_external_id_match(
        session=populated_session,
        context_excerpt="$AAPL closed up 3%.",
    )

    assert match is not None
    assert match.id == survivor.id
