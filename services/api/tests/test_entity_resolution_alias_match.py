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
    aliases: list[str],
    entity_type: EntityType = EntityType.company,
    external_ids: dict[str, str] | None = None,
) -> Entity:
    entity = Entity(
        type=entity_type.value,
        canonical_name=canonical_name,
        aliases=aliases,
        external_ids=external_ids or {},
        attributes={},
        confidence=1.0,
        needs_review=False,
    )
    session.add(entity)
    await session.flush()
    return entity


@pytest.mark.asyncio
async def test_alias_match_returns_unique_hit(populated_session: AsyncSession) -> None:
    from app.services.entity_resolution._alias_match import step_1_alias_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            aliases=["Apple", "Apple Inc."],
        )

    match = await step_1_alias_match(
        session=populated_session, candidate_text="Apple"
    )

    assert match is not None
    assert match.canonical_name == "Apple Inc."


@pytest.mark.asyncio
async def test_alias_match_returns_none_on_zero_matches(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._alias_match import step_1_alias_match

    match = await step_1_alias_match(
        session=populated_session, candidate_text="Unknown"
    )

    assert match is None


@pytest.mark.asyncio
async def test_alias_match_returns_none_on_ambiguous_hits(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._alias_match import step_1_alias_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
        )
        await _seed_entity(
            populated_session,
            canonical_name="Apple Hospitality REIT",
            aliases=["Apple"],
        )

    match = await step_1_alias_match(
        session=populated_session, candidate_text="Apple"
    )

    assert match is None


@pytest.mark.asyncio
async def test_alias_match_skips_merged_tombstones(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._alias_match import step_1_alias_match

    async with populated_session.begin():
        survivor = await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
        )
        tombstone = await _seed_entity(
            populated_session,
            canonical_name="Apple Computer, Inc.",
            aliases=["Apple"],
        )
        tombstone.merged_into_id = survivor.id

    match = await step_1_alias_match(
        session=populated_session, candidate_text="Apple"
    )

    assert match is not None
    assert match.id == survivor.id


@pytest.mark.asyncio
async def test_alias_match_is_case_sensitive(populated_session: AsyncSession) -> None:
    from app.services.entity_resolution._alias_match import step_1_alias_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
        )

    match = await step_1_alias_match(
        session=populated_session, candidate_text="apple"
    )

    assert match is None


@pytest.mark.asyncio
async def test_alias_match_handles_empty_alias_list(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._alias_match import step_1_alias_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            aliases=[],
        )

    match = await step_1_alias_match(
        session=populated_session, candidate_text="Apple"
    )

    assert match is None
