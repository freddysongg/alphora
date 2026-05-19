from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture()
async def populated_session(
    initialized_schema: None,
) -> AsyncIterator[AsyncSession]:
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def test_insert_or_get_entity_inserts_new_row(
    populated_session: AsyncSession,
) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_bootstrap._persist import insert_or_get_entity

    async with populated_session.begin():
        entity, was_inserted = await insert_or_get_entity(
            session=populated_session,
            entity_type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=["Apple", "Apple Inc."],
            external_ids={"cik": "0000320193", "ticker": "AAPL"},
            primary_external_id_key="cik",
            source_registry="sec_cik",
        )

    assert was_inserted is True
    assert entity.canonical_name == "Apple Inc."
    assert entity.external_ids["cik"] == "0000320193"
    assert entity.confidence == 1.0
    assert entity.needs_review is False
    assert entity.attributes == {"source_registry": "sec_cik"}


async def test_insert_or_get_entity_returns_existing_on_external_id_match(
    populated_session: AsyncSession,
) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_bootstrap._persist import insert_or_get_entity

    async with populated_session.begin():
        first, _ = await insert_or_get_entity(
            session=populated_session,
            entity_type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
            external_ids={"cik": "0000320193"},
            primary_external_id_key="cik",
            source_registry="sec_cik",
        )
        first_id = first.id

    async with populated_session.begin():
        second, was_inserted = await insert_or_get_entity(
            session=populated_session,
            entity_type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=["AppleComputers"],
            external_ids={"cik": "0000320193", "lei": "HWUPKR0MPOU8FGXBT394"},
            primary_external_id_key="cik",
            source_registry="gleif",
        )

    assert was_inserted is False
    assert second.id == first_id
    assert "AppleComputers" in second.aliases
    assert "Apple" in second.aliases
    assert second.external_ids.get("lei") == "HWUPKR0MPOU8FGXBT394"
    assert second.external_ids.get("cik") == "0000320193"


async def test_insert_or_get_entity_raises_when_primary_key_missing(
    populated_session: AsyncSession,
) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_bootstrap._persist import (
        BootstrapError,
        insert_or_get_entity,
    )

    with pytest.raises(BootstrapError) as excinfo:
        async with populated_session.begin():
            await insert_or_get_entity(
                session=populated_session,
                entity_type=EntityType.company,
                canonical_name="Apple Inc.",
                aliases=[],
                external_ids={"ticker": "AAPL"},
                primary_external_id_key="cik",
                source_registry="sec_cik",
            )

    assert "cik" in str(excinfo.value)


async def test_insert_or_get_entity_isolates_lookup_by_type(
    populated_session: AsyncSession,
) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_bootstrap._persist import insert_or_get_entity

    async with populated_session.begin():
        company, _ = await insert_or_get_entity(
            session=populated_session,
            entity_type=EntityType.company,
            canonical_name="United States",
            aliases=[],
            external_ids={"iso_alpha2": "US"},
            primary_external_id_key="iso_alpha2",
            source_registry="iso_3166",
        )

    async with populated_session.begin():
        country, was_inserted = await insert_or_get_entity(
            session=populated_session,
            entity_type=EntityType.country,
            canonical_name="United States",
            aliases=[],
            external_ids={"iso_alpha2": "US"},
            primary_external_id_key="iso_alpha2",
            source_registry="iso_3166",
        )

    assert was_inserted is True
    assert country.id != company.id


async def test_insert_or_get_entity_preserves_existing_external_ids_on_conflict(
    populated_session: AsyncSession,
) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_bootstrap._persist import insert_or_get_entity

    async with populated_session.begin():
        await insert_or_get_entity(
            session=populated_session,
            entity_type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=[],
            external_ids={"cik": "0000320193", "ticker": "AAPL"},
            primary_external_id_key="cik",
            source_registry="sec_cik",
        )

    async with populated_session.begin():
        merged, _ = await insert_or_get_entity(
            session=populated_session,
            entity_type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=[],
            external_ids={"cik": "0000320193", "ticker": "AAPL2"},
            primary_external_id_key="cik",
            source_registry="polygon_tickers",
        )

    assert merged.external_ids["ticker"] == "AAPL"


def test_bootstrap_error_inherits_from_exception() -> None:
    from app.services.entity_bootstrap._persist import BootstrapError

    assert issubclass(BootstrapError, Exception)
