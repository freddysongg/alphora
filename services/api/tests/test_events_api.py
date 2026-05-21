import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import (
    Entity,
    EntityType,
    EventResolution,
    Hypothesis,
    HypothesisStatus,
    Relation,
    RelationType,
)
from app.services.belief import ensure_hypothesis_entity


@pytest.fixture()
async def async_client(initialized_schema: None, fake_queue) -> AsyncClient:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _seed_event(session: AsyncSession, *, name: str = "Earnings Q3") -> Entity:
    entity = Entity(
        type=EntityType.event.value,
        canonical_name=name,
        aliases=[name],
        external_ids={},
        attributes={},
    )
    session.add(entity)
    await session.flush()
    return entity


async def _seed_hypothesis_with_entity(
    session: AsyncSession,
    *,
    claim_text: str,
    status_value: str = HypothesisStatus.active.value,
) -> Hypothesis:
    row = Hypothesis(
        claim_text=claim_text,
        scope_entity_ids=[],
        scope_theme_ids=[],
        status=status_value,
    )
    session.add(row)
    await session.flush()
    await ensure_hypothesis_entity(session=session, hypothesis=row)
    return row


async def _bind(
    session: AsyncSession,
    *,
    event: Entity,
    hypothesis_entity_id: uuid.UUID,
    relation_type: RelationType,
) -> None:
    relation = Relation(
        from_id=event.id,
        to_id=hypothesis_entity_id,
        type=relation_type.value,
        attributes={},
        is_explicit=True,
        sign=1.0,
    )
    session.add(relation)
    await session.flush()


@pytest.mark.asyncio
async def test_resolve_event_validates_bound_hypothesis_on_beat(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    event = await _seed_event(db_session)
    hypothesis = await _seed_hypothesis_with_entity(
        db_session, claim_text="will beat consensus"
    )
    assert hypothesis.entity_id is not None
    await _bind(
        db_session,
        event=event,
        hypothesis_entity_id=hypothesis.entity_id,
        relation_type=RelationType.validates_if_beat,
    )
    await db_session.commit()

    hypothesis_id = hypothesis.id
    response = await async_client.post(
        f"/api/research/events/{event.id}/resolve",
        json={"kind": "beat", "notes": "EPS +12%"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resolution"]["kind"] == "beat"
    assert str(hypothesis_id) in body["validated_hypothesis_ids"]
    assert body["falsified_hypothesis_ids"] == []

    db_session.expire_all()
    refreshed = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == hypothesis_id)
        )
    ).scalar_one()
    assert refreshed.status == HypothesisStatus.validated.value


@pytest.mark.asyncio
async def test_resolve_event_falsifies_bound_hypothesis_on_miss(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    event = await _seed_event(db_session)
    hypothesis = await _seed_hypothesis_with_entity(
        db_session, claim_text="will miss"
    )
    assert hypothesis.entity_id is not None
    await _bind(
        db_session,
        event=event,
        hypothesis_entity_id=hypothesis.entity_id,
        relation_type=RelationType.falsifies_if_miss,
    )
    await db_session.commit()

    response = await async_client.post(
        f"/api/research/events/{event.id}/resolve",
        json={"kind": "miss"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert str(hypothesis.id) in body["falsified_hypothesis_ids"]
    assert body["validated_hypothesis_ids"] == []


@pytest.mark.asyncio
async def test_resolve_event_rejects_unknown_kind(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    event = await _seed_event(db_session)
    await db_session.commit()
    response = await async_client.post(
        f"/api/research/events/{event.id}/resolve",
        json={"kind": "explosion"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_resolve_event_returns_404_when_event_missing(
    async_client: AsyncClient,
) -> None:
    response = await async_client.post(
        f"/api/research/events/{uuid.uuid4()}/resolve",
        json={"kind": "beat"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_resolve_event_returns_404_when_entity_is_not_event(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    entity = Entity(
        type=EntityType.company.value,
        canonical_name="NVDA",
        aliases=["NVDA"],
        external_ids={},
        attributes={},
    )
    db_session.add(entity)
    await db_session.commit()
    response = await async_client.post(
        f"/api/research/events/{entity.id}/resolve",
        json={"kind": "beat"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_resolve_event_persists_resolution_row(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    event = await _seed_event(db_session)
    await db_session.commit()
    response = await async_client.post(
        f"/api/research/events/{event.id}/resolve",
        json={"kind": "neutral", "notes": "no surprise"},
    )
    assert response.status_code == 200, response.text
    rows = (
        (
            await db_session.execute(
                select(EventResolution).where(
                    EventResolution.event_entity_id == event.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].kind == "neutral"
    assert rows[0].notes == "no surprise"


@pytest.mark.asyncio
async def test_list_event_resolutions_returns_ordered_history(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    event = await _seed_event(db_session)
    await db_session.commit()
    await async_client.post(
        f"/api/research/events/{event.id}/resolve",
        json={"kind": "neutral"},
    )
    await async_client.post(
        f"/api/research/events/{event.id}/resolve",
        json={"kind": "beat"},
    )

    response = await async_client.get(
        f"/api/research/events/{event.id}/resolutions"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 2
    timestamps = [item["resolved_at"] for item in body]
    assert timestamps == sorted(timestamps, reverse=True)
