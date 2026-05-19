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


async def test_fetch_existing_by_primary_value_returns_map_keyed_by_external_id(
    populated_session: AsyncSession,
) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_bootstrap._persist import (
        fetch_existing_by_primary_value,
        insert_or_get_entity,
    )

    async with populated_session.begin():
        await insert_or_get_entity(
            session=populated_session,
            entity_type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=[],
            external_ids={"cik": "0000320193"},
            primary_external_id_key="cik",
            source_registry="sec_cik",
        )
        await insert_or_get_entity(
            session=populated_session,
            entity_type=EntityType.company,
            canonical_name="Microsoft Corp.",
            aliases=[],
            external_ids={"cik": "0000789019"},
            primary_external_id_key="cik",
            source_registry="sec_cik",
        )

    cache = await fetch_existing_by_primary_value(
        session=populated_session,
        entity_type=EntityType.company,
        primary_external_id_key="cik",
    )

    assert set(cache.keys()) == {"0000320193", "0000789019"}
    assert cache["0000320193"].canonical_name == "Apple Inc."


async def test_fetch_existing_by_primary_value_skips_rows_missing_primary_key(
    populated_session: AsyncSession,
) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_bootstrap._persist import (
        fetch_existing_by_primary_value,
        insert_or_get_entity,
    )

    async with populated_session.begin():
        await insert_or_get_entity(
            session=populated_session,
            entity_type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=[],
            external_ids={"cik": "0000320193"},
            primary_external_id_key="cik",
            source_registry="sec_cik",
        )
        await insert_or_get_entity(
            session=populated_session,
            entity_type=EntityType.company,
            canonical_name="LEI-only Co",
            aliases=[],
            external_ids={"lei": "ABC"},
            primary_external_id_key="lei",
            source_registry="gleif",
        )

    cache = await fetch_existing_by_primary_value(
        session=populated_session,
        entity_type=EntityType.company,
        primary_external_id_key="cik",
    )

    assert set(cache.keys()) == {"0000320193"}


async def test_insert_or_get_entity_uses_supplied_cache_for_lookup_and_insert(
    populated_session: AsyncSession,
) -> None:
    from app.db.models_graph import Entity, EntityType
    from app.services.entity_bootstrap._persist import (
        fetch_existing_by_primary_value,
        insert_or_get_entity,
    )

    async with populated_session.begin():
        seeded, _ = await insert_or_get_entity(
            session=populated_session,
            entity_type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
            external_ids={"cik": "0000320193"},
            primary_external_id_key="cik",
            source_registry="sec_cik",
        )
        seeded_id = seeded.id

    async with populated_session.begin():
        cache: dict[str, Entity] = await fetch_existing_by_primary_value(
            session=populated_session,
            entity_type=EntityType.company,
            primary_external_id_key="cik",
        )
        hit, hit_was_inserted = await insert_or_get_entity(
            session=populated_session,
            entity_type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=["Apple Computer"],
            external_ids={"cik": "0000320193"},
            primary_external_id_key="cik",
            source_registry="sec_cik",
            existing_by_primary_value=cache,
        )
        new_row, new_was_inserted = await insert_or_get_entity(
            session=populated_session,
            entity_type=EntityType.company,
            canonical_name="Microsoft Corp.",
            aliases=[],
            external_ids={"cik": "0000789019"},
            primary_external_id_key="cik",
            source_registry="sec_cik",
            existing_by_primary_value=cache,
        )

    assert hit_was_inserted is False
    assert hit.id == seeded_id
    assert new_was_inserted is True
    assert cache["0000789019"] is new_row


async def test_bootstrap_emits_single_entities_select_per_run(
    initialized_schema: None,
) -> None:
    from sqlalchemy import event

    from app.db.session import engine, session_factory
    from app.services.entity_bootstrap.sec_cik import bootstrap_from_sec_cik
    from app.services.source_clients.sec_edgar import (
        SecCompanyTicker,
        SecCompanyTickersResponse,
    )

    payload = SecCompanyTickersResponse(
        companies=[
            SecCompanyTicker(cik_str=cik, ticker=f"T{cik}", title=f"Company {cik}")
            for cik in range(1, 11)
        ]
    )

    select_count = 0

    def _on_cursor_execute(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        nonlocal select_count
        normalized = statement.upper().replace('"', "").replace("`", "")
        if "FROM ENTITIES" in normalized:
            select_count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", _on_cursor_execute)
    try:
        async with session_factory() as session:
            await bootstrap_from_sec_cik(session=session, payload=payload)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _on_cursor_execute)

    assert select_count == 1, (
        f"expected 1 SELECT FROM entities for the prefetch, got {select_count}; "
        "regression: per-record full table scan reintroduced"
    )
