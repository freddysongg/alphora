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


async def test_bootstrap_from_congress_bioguide_creates_person_entities(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.congress_bioguide import (
        CongressMemberRecord,
        bootstrap_from_congress_bioguide,
    )

    async def fake_fetcher() -> list[CongressMemberRecord]:
        return [
            CongressMemberRecord(
                bioguide_id="P000197",
                full_name="Nancy Pelosi",
                party="D",
                state="CA",
                chamber="house",
            ),
            CongressMemberRecord(
                bioguide_id="S001230",
                full_name="Brian Schatz",
                party="D",
                state="HI",
                chamber="senate",
            ),
        ]

    results = await bootstrap_from_congress_bioguide(
        session=populated_session, fetcher=fake_fetcher
    )

    assert len(results) == 2
    pelosi = next(r for r in results if r.canonical_name == "Nancy Pelosi")
    assert pelosi.external_ids["bioguide_id"] == "P000197"
    assert pelosi.external_ids["party"] == "D"
    assert pelosi.external_ids["state"] == "CA"
    assert pelosi.external_ids["chamber"] == "house"
    assert pelosi.source_registry == "congress_bioguide"


async def test_bootstrap_from_congress_via_respx_mocked_endpoint(
    populated_session: AsyncSession,
) -> None:
    import httpx
    import respx

    from app.services.entity_bootstrap.congress_bioguide import (
        CongressMemberRecord,
        bootstrap_from_congress_bioguide,
    )

    payload = {
        "members": [
            {
                "bioguideId": "P000197",
                "name": "Nancy Pelosi",
                "partyName": "Democratic",
                "state": "CA",
                "chamber": "House",
            }
        ]
    }

    with respx.mock(base_url="https://api.congress.gov/v3") as mock:
        mock.get("/member").mock(return_value=httpx.Response(200, json=payload))

        async def fetcher() -> list[CongressMemberRecord]:
            async with httpx.AsyncClient(
                base_url="https://api.congress.gov/v3"
            ) as client:
                response = await client.get("/member")
                response.raise_for_status()
                records: list[CongressMemberRecord] = []
                for row in response.json()["members"]:
                    records.append(
                        CongressMemberRecord(
                            bioguide_id=row["bioguideId"],
                            full_name=row["name"],
                            party=row["partyName"][:1],
                            state=row["state"],
                            chamber=row["chamber"].lower(),
                        )
                    )
                return records

        results = await bootstrap_from_congress_bioguide(
            session=populated_session, fetcher=fetcher
        )

    assert len(results) == 1
    assert results[0].external_ids["bioguide_id"] == "P000197"


async def test_bootstrap_from_congress_is_idempotent(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.congress_bioguide import (
        CongressMemberRecord,
        bootstrap_from_congress_bioguide,
    )

    async def fake_fetcher() -> list[CongressMemberRecord]:
        return [
            CongressMemberRecord(
                bioguide_id="P000197",
                full_name="Nancy Pelosi",
                party="D",
                state="CA",
                chamber="house",
            )
        ]

    first = await bootstrap_from_congress_bioguide(
        session=populated_session, fetcher=fake_fetcher
    )
    second = await bootstrap_from_congress_bioguide(
        session=populated_session, fetcher=fake_fetcher
    )

    assert first[0].entity_id == second[0].entity_id
