import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import DataSource
from app.services.data_sources_bootstrap import (
    KNOWN_DATA_SOURCES,
    DataSourceSeed,
    bootstrap_data_sources,
)


@pytest.mark.asyncio
async def test_bootstrap_inserts_all_known_sources_on_empty_db(
    db_session: AsyncSession,
) -> None:
    result = await bootstrap_data_sources(session=db_session)
    rows = (await db_session.execute(select(DataSource))).scalars().all()

    assert result.inserted == len(KNOWN_DATA_SOURCES)
    assert result.updated == 0
    assert result.unchanged == 0
    assert len(rows) == len(KNOWN_DATA_SOURCES)


@pytest.mark.asyncio
async def test_bootstrap_known_sources_includes_phase7_additions(
    db_session: AsyncSession,
) -> None:
    await bootstrap_data_sources(session=db_session)
    rows = (await db_session.execute(select(DataSource))).scalars().all()
    names = {row.name for row in rows}

    for required in (
        "capitol_trades",
        "polymarket_data",
        "finnhub_news",
        "cme_fedwatch",
        "fed_press",
        "gdelt",
    ):
        assert required in names, f"missing Phase 7 source registration: {required}"


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent_on_second_run(
    db_session: AsyncSession,
) -> None:
    first = await bootstrap_data_sources(session=db_session)
    second = await bootstrap_data_sources(session=db_session)

    assert first.inserted == len(KNOWN_DATA_SOURCES)
    assert second.inserted == 0
    assert second.updated == 0
    assert second.unchanged == len(KNOWN_DATA_SOURCES)

    rows = (await db_session.execute(select(DataSource))).scalars().all()
    assert len(rows) == len(KNOWN_DATA_SOURCES)


@pytest.mark.asyncio
async def test_bootstrap_updates_only_changed_fields(
    db_session: AsyncSession,
) -> None:
    seed = DataSourceSeed(
        name="experimental_feed",
        kind="news",
        description="initial description",
        homepage_url="https://example.com",
        reliability_score=0.5,
    )
    await bootstrap_data_sources(session=db_session, seeds=[seed])
    pre = (
        await db_session.execute(
            select(DataSource).where(DataSource.name == "experimental_feed")
        )
    ).scalar_one()
    original_id = pre.id

    updated_seed = DataSourceSeed(
        name="experimental_feed",
        kind="news",
        description="refined description",
        homepage_url="https://example.com",
        reliability_score=0.7,
    )
    result = await bootstrap_data_sources(session=db_session, seeds=[updated_seed])

    post = (
        await db_session.execute(
            select(DataSource).where(DataSource.name == "experimental_feed")
        )
    ).scalar_one()
    assert post.id == original_id
    assert post.description == "refined description"
    assert post.reliability_score == 0.7
    assert result.inserted == 0
    assert result.updated == 1


@pytest.mark.asyncio
async def test_bootstrap_reliability_scores_are_in_unit_range(
    db_session: AsyncSession,
) -> None:
    """Sanity check: every seeded reliability score sits in (0, 1)."""
    for seed in KNOWN_DATA_SOURCES:
        assert 0.0 < seed.reliability_score <= 1.0, seed.name


def test_known_data_sources_have_unique_names() -> None:
    names = [seed.name for seed in KNOWN_DATA_SOURCES]
    assert len(names) == len(set(names))
