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


async def test_bootstrap_from_gleif_creates_entities_with_lei(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.gleif import (
        GleifRecord,
        bootstrap_from_gleif,
    )

    async def fake_fetcher() -> list[GleifRecord]:
        return [
            GleifRecord(
                lei="HWUPKR0MPOU8FGXBT394",
                legal_name="Apple Inc.",
                other_names=["Apple Computer, Inc."],
                jurisdiction="US",
            ),
            GleifRecord(
                lei="INR2EJN1ERAN0W5ZP974",
                legal_name="Microsoft Corporation",
                other_names=[],
                jurisdiction="US",
            ),
        ]

    results = await bootstrap_from_gleif(
        session=populated_session, fetcher=fake_fetcher
    )

    assert len(results) == 2
    apple = next(r for r in results if r.canonical_name == "Apple Inc.")
    assert apple.external_ids["lei"] == "HWUPKR0MPOU8FGXBT394"
    assert apple.external_ids["jurisdiction"] == "US"
    assert "Apple Computer, Inc." in apple.aliases
    assert apple.source_registry == "gleif"


async def test_bootstrap_from_gleif_via_respx_mocked_endpoint(
    populated_session: AsyncSession,
) -> None:
    import httpx
    import respx

    from app.services.entity_bootstrap.gleif import (
        GleifRecord,
        bootstrap_from_gleif,
    )

    payload = {
        "data": [
            {
                "id": "HWUPKR0MPOU8FGXBT394",
                "attributes": {
                    "entity": {
                        "legalName": {"name": "Apple Inc."},
                        "otherNames": [{"name": "Apple Computer, Inc."}],
                        "jurisdiction": "US",
                    }
                },
            }
        ]
    }

    with respx.mock(base_url="https://api.gleif.org/api/v1") as mock:
        mock.get("/lei-records").mock(return_value=httpx.Response(200, json=payload))

        async def fetcher() -> list[GleifRecord]:
            async with httpx.AsyncClient(base_url="https://api.gleif.org/api/v1") as client:
                response = await client.get("/lei-records")
                response.raise_for_status()
                records: list[GleifRecord] = []
                for row in response.json()["data"]:
                    entity = row["attributes"]["entity"]
                    records.append(
                        GleifRecord(
                            lei=row["id"],
                            legal_name=entity["legalName"]["name"],
                            other_names=[
                                other["name"] for other in entity.get("otherNames", [])
                            ],
                            jurisdiction=entity["jurisdiction"],
                        )
                    )
                return records

        results = await bootstrap_from_gleif(
            session=populated_session, fetcher=fetcher
        )

    assert len(results) == 1
    assert results[0].external_ids["lei"] == "HWUPKR0MPOU8FGXBT394"


async def test_bootstrap_from_gleif_is_idempotent(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.gleif import (
        GleifRecord,
        bootstrap_from_gleif,
    )

    async def fake_fetcher() -> list[GleifRecord]:
        return [
            GleifRecord(
                lei="HWUPKR0MPOU8FGXBT394",
                legal_name="Apple Inc.",
                other_names=[],
                jurisdiction="US",
            )
        ]

    first = await bootstrap_from_gleif(session=populated_session, fetcher=fake_fetcher)
    second = await bootstrap_from_gleif(session=populated_session, fetcher=fake_fetcher)

    assert first[0].entity_id == second[0].entity_id


def test_gleif_record_is_frozen() -> None:
    import pydantic

    from app.services.entity_bootstrap.gleif import GleifRecord

    record = GleifRecord(
        lei="X",
        legal_name="Y",
        other_names=[],
        jurisdiction="US",
    )
    with pytest.raises(pydantic.ValidationError):
        record.lei = "Z"  # type: ignore[misc]
