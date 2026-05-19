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
    aliases: list[str] | None = None,
    entity_type: EntityType = EntityType.company,
) -> Entity:
    entity = Entity(
        type=entity_type.value,
        canonical_name=canonical_name,
        aliases=aliases or [],
        external_ids={},
        attributes={},
        confidence=1.0,
        needs_review=False,
    )
    session.add(entity)
    await session.flush()
    return entity


@pytest.mark.asyncio
async def test_fuzzy_match_returns_unique_high_score(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._fuzzy_match import step_3_fuzzy_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            aliases=["Apple Inc.", "Apple"],
        )
        await _seed_entity(
            populated_session,
            canonical_name="Microsoft Corp.",
            aliases=["Microsoft"],
        )

    match, score = await step_3_fuzzy_match(
        session=populated_session, candidate_text="Apple Inc"
    )

    assert match is not None
    assert match.canonical_name == "Apple Inc."
    assert score >= 0.85


@pytest.mark.asyncio
async def test_fuzzy_match_falls_through_below_threshold(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._fuzzy_match import step_3_fuzzy_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
        )

    match, _score = await step_3_fuzzy_match(
        session=populated_session, candidate_text="Tesla"
    )

    assert match is None


@pytest.mark.asyncio
async def test_fuzzy_match_falls_through_on_two_close_matches(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._fuzzy_match import step_3_fuzzy_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
        )
        await _seed_entity(
            populated_session,
            canonical_name="Apple Hospitality",
            aliases=["Apple Hospitality"],
        )

    match, _score = await step_3_fuzzy_match(
        session=populated_session, candidate_text="Apple"
    )

    assert match is None


@pytest.mark.asyncio
async def test_fuzzy_match_strips_suffix_for_comparison(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._fuzzy_match import step_3_fuzzy_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Apple",
            aliases=["Apple"],
        )
        await _seed_entity(
            populated_session,
            canonical_name="Microsoft Corp.",
            aliases=["Microsoft"],
        )

    match, score = await step_3_fuzzy_match(
        session=populated_session, candidate_text="Apple Inc."
    )

    assert match is not None
    assert match.canonical_name == "Apple"
    assert score >= 0.85


@pytest.mark.asyncio
async def test_fuzzy_match_returns_none_for_empty_candidate(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._fuzzy_match import step_3_fuzzy_match

    async with populated_session.begin():
        await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
        )

    match, score = await step_3_fuzzy_match(
        session=populated_session, candidate_text="   "
    )

    assert match is None
    assert score == 0.0


@pytest.mark.asyncio
async def test_fuzzy_match_returns_none_for_empty_table(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._fuzzy_match import step_3_fuzzy_match

    match, score = await step_3_fuzzy_match(
        session=populated_session, candidate_text="Apple"
    )

    assert match is None
    assert score == 0.0


@pytest.mark.asyncio
async def test_fuzzy_match_skips_merged_tombstones(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_resolution._fuzzy_match import step_3_fuzzy_match

    async with populated_session.begin():
        survivor = await _seed_entity(
            populated_session,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
        )
        tombstone = await _seed_entity(
            populated_session,
            canonical_name="Apple Computer, Inc.",
            aliases=["Apple Computer"],
        )
        tombstone.merged_into_id = survivor.id

    match, score = await step_3_fuzzy_match(
        session=populated_session, candidate_text="Apple Inc"
    )

    assert match is not None
    assert match.id == survivor.id
    assert score >= 0.85
