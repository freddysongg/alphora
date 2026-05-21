"""API tests for the weekly human review endpoints."""

import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_evals import HumanReview
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.db.session import session_factory


@pytest.fixture()
async def async_client(initialized_schema: None, fake_queue) -> AsyncClient:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        trade_date=date(2026, 5, 19),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.succeeded,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.flush()
    return run.id


async def test_create_human_review_persists_two_axis_score(
    async_client: AsyncClient,
) -> None:
    payload = {
        "week_start": "2026-05-18",
        "reviewer": "alice",
        "surfaced_missed": 2,
        "missed_noticed": -1,
        "notes": "macro brief flagged the sector rotation I'd missed",
        "brief_kind": "macro",
    }
    response = await async_client.post("/api/human-reviews", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["reviewer"] == "alice"
    assert body["surfaced_missed"] == 2
    assert body["missed_noticed"] == -1
    assert body["week_start"] == "2026-05-18"
    assert body["brief_kind"] == "macro"
    assert body["run_id"] is None


async def test_create_human_review_with_run_id_validates_existence(
    async_client: AsyncClient,
) -> None:
    response = await async_client.post(
        "/api/human-reviews",
        json={
            "run_id": str(uuid.uuid4()),
            "week_start": "2026-05-18",
            "reviewer": "alice",
            "surfaced_missed": 0,
            "missed_noticed": 0,
        },
    )
    assert response.status_code == 404


async def test_create_human_review_rejects_out_of_range_axis_values(
    async_client: AsyncClient,
) -> None:
    response = await async_client.post(
        "/api/human-reviews",
        json={
            "week_start": "2026-05-18",
            "reviewer": "alice",
            "surfaced_missed": 5,
            "missed_noticed": 0,
        },
    )
    assert response.status_code == 422


async def test_list_human_reviews_filters_by_week_start(
    async_client: AsyncClient,
) -> None:
    async with session_factory() as session:
        session.add(
            HumanReview(
                week_start=date(2026, 5, 11),
                reviewer="alice",
                surfaced_missed=1,
                missed_noticed=0,
            )
        )
        session.add(
            HumanReview(
                week_start=date(2026, 5, 18),
                reviewer="alice",
                surfaced_missed=2,
                missed_noticed=-1,
            )
        )
        await session.commit()
    response = await async_client.get(
        "/api/human-reviews", params={"week_start": "2026-05-18"}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["week_start"] == "2026-05-18"
    assert body[0]["surfaced_missed"] == 2


async def test_list_human_reviews_filters_by_run_id(
    async_client: AsyncClient,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        session.add(
            HumanReview(
                run_id=run_id,
                week_start=date(2026, 5, 18),
                reviewer="alice",
                surfaced_missed=2,
                missed_noticed=0,
            )
        )
        session.add(
            HumanReview(
                run_id=None,
                week_start=date(2026, 5, 18),
                reviewer="bob",
                surfaced_missed=0,
                missed_noticed=2,
            )
        )
        await session.commit()
    response = await async_client.get(
        "/api/human-reviews", params={"run_id": str(run_id)}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["run_id"] == str(run_id)


async def test_get_human_review_summary_returns_per_week_means(
    async_client: AsyncClient,
) -> None:
    async with session_factory() as session:
        for axis_pair in [(2, 0), (1, -1), (0, 1)]:
            surfaced, missed = axis_pair
            session.add(
                HumanReview(
                    week_start=date(2026, 5, 18),
                    reviewer="alice",
                    surfaced_missed=surfaced,
                    missed_noticed=missed,
                )
            )
        session.add(
            HumanReview(
                week_start=date(2026, 5, 11),
                reviewer="bob",
                surfaced_missed=-1,
                missed_noticed=2,
            )
        )
        await session.commit()
    response = await async_client.get("/api/human-reviews/summary")
    assert response.status_code == 200
    body = response.json()
    weeks = {w["week_start"]: w for w in body["weeks"]}
    assert weeks["2026-05-18"]["review_count"] == 3
    assert pytest.approx(weeks["2026-05-18"]["mean_surfaced_missed"], rel=1e-9) == 1.0
    assert pytest.approx(weeks["2026-05-18"]["mean_missed_noticed"], rel=1e-9) == 0.0
    assert weeks["2026-05-11"]["review_count"] == 1
    assert pytest.approx(weeks["2026-05-11"]["mean_surfaced_missed"], rel=1e-9) == -1.0


async def test_get_human_review_summary_caps_to_weeks_parameter(
    async_client: AsyncClient,
) -> None:
    async with session_factory() as session:
        for offset in range(5):
            session.add(
                HumanReview(
                    week_start=date(2026, 4, 6).replace(day=6 + offset),
                    reviewer="alice",
                    surfaced_missed=1,
                    missed_noticed=0,
                )
            )
        await session.commit()
    response = await async_client.get(
        "/api/human-reviews/summary", params={"weeks": 2}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["weeks"]) == 2


async def test_list_human_reviews_filters_by_brief_kind(
    async_client: AsyncClient,
) -> None:
    async with session_factory() as session:
        session.add(
            HumanReview(
                week_start=date(2026, 5, 18),
                reviewer="alice",
                brief_kind="sector",
                surfaced_missed=1,
                missed_noticed=0,
            )
        )
        session.add(
            HumanReview(
                week_start=date(2026, 5, 18),
                reviewer="bob",
                brief_kind="company",
                surfaced_missed=0,
                missed_noticed=1,
            )
        )
        await session.commit()
    response = await async_client.get(
        "/api/human-reviews", params={"brief_kind": "company"}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["brief_kind"] == "company"


async def test_create_human_review_round_trips_db(
    async_client: AsyncClient,
) -> None:
    response = await async_client.post(
        "/api/human-reviews",
        json={
            "week_start": "2026-05-18",
            "reviewer": "alice",
            "surfaced_missed": 1,
            "missed_noticed": -1,
        },
    )
    assert response.status_code == 201
    review_id = response.json()["id"]
    async with session_factory() as session:
        row = (
            await session.execute(
                select(HumanReview).where(HumanReview.id == uuid.UUID(review_id))
            )
        ).scalar_one()
        assert row.surfaced_missed == 1
        assert row.missed_noticed == -1
