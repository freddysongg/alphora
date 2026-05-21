import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_bootstrap_returns_eleven_sector_entities(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research._bootstrap import run

    entities = await run(session=db_session)
    assert len(entities) == 11
    names = {e.canonical_name for e in entities}
    assert "Energy" in names
    assert "Real Estate" in names


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent_under_double_call(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research._bootstrap import run

    first = await run(session=db_session)
    second = await run(session=db_session)
    assert {e.entity_id for e in first} == {e.entity_id for e in second}
